"""Ativação interna após consentimento e prova de e-mail, sem exigir Nuvemshop.

A feature flag fica OFF até a homologação manual. Nunca credita pontos e
nunca transforma compradores importados em participantes sem autorização.
"""
from django.conf import settings
from django.db import transaction
from apps.tenants.models import Tenant
from apps.customers.services import attach_verified_contact

from .email_proof import digest
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission
from .models import ProgramParticipant


def club_activates_on_email(tenant_id) -> bool:
    """Loja com o clube configurado: e-mail confirmado JÁ É participação ativa, sem aprovação
    nem vínculo com a Nuvemshop (que vira complemento). Sem clube, vale a flag antiga."""
    from apps.sales.models import CounterPilot
    return (getattr(settings, "FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED", False)
            or CounterPilot.objects.filter(tenant_id=tenant_id).exists())


@transaction.atomic
def activate_standalone_after_email(token: str) -> bool:
    challenge = EnrollmentEmailChallenge.objects.filter(
        token_digest=digest(token), purpose=EnrollmentEmailChallenge.Purpose.VERIFY,
        consumed_at__isnull=False,
    ).values("submission_id", "submission__tenant_id").first()
    if not challenge or not club_activates_on_email(challenge["submission__tenant_id"]):
        return False
    outcome = activate_verified_submission(challenge["submission_id"])
    # Participação ativa com e-mail confirmado: pedidos do site feitos depois da adesão contam.
    member = EnrollmentSubmission.objects.filter(pk=challenge["submission_id"]).values_list(
        "participant_id", flat=True).first()
    if member:
        from apps.sales.online import queue_credit_since_join
        queue_credit_since_join(member)
    # Cadastro feito pela loja: a participação já existia; agora o e-mail também está confirmado.
    return outcome in ("created", "joined_existing", "skipped:already_member")


@transaction.atomic
def activate_verified_submission(submission_id) -> str:
    """Ativa um cadastro com aceite e e-mail confirmado que ainda não virou participante.

    "created": nova participação ativa. "joined_existing": já havia participação ATIVA com o
    mesmo e-mail nesta loja (cadastro repetido): o cadastro passa a apontar para ela, sem
    criar outra pessoa. Outros resultados ("skipped:<motivo>") não mudam nada.
    Usado na confirmação do e-mail e pelo comando activate_verified_members.
    """
    sub = EnrollmentSubmission.objects.select_related("tenant", "terms").get(pk=submission_id)
    # Trava do tenant impede corrida de dois aceites do mesmo e-mail.
    tenant = Tenant.objects.select_for_update().get(pk=sub.tenant_id)
    submission = EnrollmentSubmission.objects.select_for_update().get(pk=sub.id)
    if tenant.status != Tenant.Status.ACTIVE:
        return "skipped:store_inactive"
    if (submission.status != EnrollmentSubmission.Status.EMAIL_VERIFIED
            or submission.email_verified_at is None):
        return "skipped:not_verified"
    if submission.withdrawn_at is not None:
        return "skipped:withdrawn"
    if submission.participant_id is not None:
        return "skipped:already_member"
    # Uma pessoa já inscrita neste mesmo tenant não vira outra por novo formulário.
    same = list(ProgramParticipant.objects.filter(
        tenant=tenant, contact_email__iexact=submission.email,
        status__in=(ProgramParticipant.Status.ACTIVE, ProgramParticipant.Status.PAUSED),
    )[:2])
    if same:
        if len(same) != 1 or same[0].status != ProgramParticipant.Status.ACTIVE:
            return "skipped:existing_needs_review"
        if EnrollmentSubmission.objects.filter(participant=same[0]).exists():
            return "skipped:duplicate_signup"     # a pessoa já entra pelo cadastro anterior
        submission.participant = same[0]
        submission.status = EnrollmentSubmission.Status.MEMBER
        submission.save(update_fields=["participant", "status"])
        return "joined_existing"
    participant = ProgramParticipant.objects.create(
        tenant=tenant, external_customer_id=None,
        display_name=submission.name, contact_email=submission.email,
        consent_at=submission.accepted_at,
        consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
        terms_version=submission.terms.version,
        status=ProgramParticipant.Status.ACTIVE,
    )
    submission.participant = participant
    submission.status = EnrollmentSubmission.Status.MEMBER
    submission.save(update_fields=["participant", "status"])
    from .phone import copy_submission_phone
    copy_submission_phone(submission, participant)
    attach_verified_contact(
        tenant_id=tenant.pk, participant_id=participant.pk,
        email=submission.email, proof_method="email_otp",
    )
    return "created"
