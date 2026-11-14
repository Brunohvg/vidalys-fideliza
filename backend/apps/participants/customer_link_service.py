"""Única operação de escrita para vínculos de clientes verificados.

A prévia, o modo manual e a confirmação automática nunca criam créditos.
A consulta remota é executada ANTES, por uma rotina API com OAuth restrito.
Este serviço revalida o estado local sob lock do tenant no banco.
"""
from django.db import transaction

from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.privacy_models import PrivacyWebhookRequest
from apps.nuvemshop.scopes import has_customer_access
from apps.tenants.models import Tenant
from apps.customers.services import attach_channel_reference, attach_verified_contact

from .enrollment_models import EnrollmentCustomerLink, EnrollmentSubmission
from .models import ProgramParticipant


class CustomerLinkConflict(ValueError):
    """Exige revisão ou nova autorização; jamais deduzir vínculo pelo e-mail."""


@transaction.atomic
def link_verified_submission(
    *, tenant_id, submission_id, customer_id: str,
    client_id: str, store_id: str, actor=None,
    source: str = "nuvemshop_customer_email_match",
):
    """(link, created); idempotente e isolado por loja.

    Chamador deve ter confirmado EXATAMENTE uma conta com e-mail igual
    pela API oficial de customers, usando o token da mesma instalação.
    """
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
    if tenant.status != Tenant.Status.ACTIVE or tenant.platform != "nuvemshop":
        raise CustomerLinkConflict("Loja não está ativa.")
    if not tenant.external_store_id or str(tenant.external_store_id) != str(store_id):
        raise CustomerLinkConflict("Conexão de loja alterada.")
    installed=NuvemshopInstallation.objects.filter(tenant=tenant).first()
    if (not installed or installed.client_id != client_id or
            installed.store_id != str(store_id) or not
            has_customer_access(installed.scope, customer_preview_enabled=True)):
        raise CustomerLinkConflict("Conexão sem permissão suficiente.")
    submission=EnrollmentSubmission.objects.select_for_update().select_related(
        "terms"
    ).get(pk=submission_id, tenant=tenant)
    if submission.status==EnrollmentSubmission.Status.LINKED:
        link=EnrollmentCustomerLink.objects.select_related("participant").filter(
            tenant=tenant,submission=submission,
        ).first()
        if (link and link.external_customer_id == customer_id and
                link.participant.status == ProgramParticipant.Status.ACTIVE):
            return link, False
        raise CustomerLinkConflict("O vínculo anterior exige revisão.")
    if (submission.status not in (
            EnrollmentSubmission.Status.EMAIL_VERIFIED,
            EnrollmentSubmission.Status.MEMBER,
        )
            or submission.email_verified_at is None
            or submission.withdrawn_at is not None
            or not submission.email):
        raise CustomerLinkConflict("Esta solicitação não está elegível.")
    if PrivacyWebhookRequest.objects.filter(
        store_id=str(store_id),customer_id=customer_id,
        topic=PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
    ).exists():
        raise CustomerLinkConflict("O titular tem pedido anterior de eliminação.")
    if (EnrollmentCustomerLink.objects.filter(
            tenant=tenant,external_customer_id=customer_id).exists() or
            ProgramParticipant.objects.filter(
                tenant=tenant,external_customer_id=customer_id).exists()):
        raise CustomerLinkConflict("Cadastro já vinculado ou pendente de revisão.")
    if submission.participant_id:
        participant=ProgramParticipant.objects.select_for_update().get(
            pk=submission.participant_id, tenant=tenant,
        )
        if (participant.status != ProgramParticipant.Status.ACTIVE
                or participant.contact_email.strip().casefold() !=
                   submission.email.strip().casefold()
                or participant.external_customer_id not in (None, customer_id)):
            raise CustomerLinkConflict("Participante interno exige revisão.")
        participant.external_customer_id=customer_id
        participant.save(update_fields=["external_customer_id"])
    else:
        participant=ProgramParticipant.objects.create(
            tenant=tenant,external_customer_id=customer_id,
            display_name=submission.name,contact_email=submission.email,
            consent_at=submission.accepted_at,
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version=submission.terms.version,
            status=ProgramParticipant.Status.ACTIVE,
        )
    link=EnrollmentCustomerLink.objects.create(
        tenant=tenant, submission=submission, participant=participant,
        external_customer_id=customer_id,confirmed_by=actor,source=source,
    )
    submission.status=EnrollmentSubmission.Status.LINKED
    submission.participant=participant
    submission.save(update_fields=["status", "participant"])
    # Fluxo existente já conferiu e-mail, tenant, OAuth e identidade exata.
    attach_verified_contact(
        tenant_id=tenant.pk, participant_id=participant.pk,
        email=submission.email, proof_method="email_otp",
    )
    attach_channel_reference(
        tenant_id=tenant.pk, participant_id=participant.pk,
        channel="nuvemshop", external_id=customer_id,
    )
    return link, True
