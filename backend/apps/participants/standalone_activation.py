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


@transaction.atomic
def activate_standalone_after_email(token: str) -> bool:
    if not getattr(settings, "FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED", False):
        return False
    challenge = EnrollmentEmailChallenge.objects.filter(
        token_digest=digest(token), purpose=EnrollmentEmailChallenge.Purpose.VERIFY,
        consumed_at__isnull=False,
    ).values("submission_id").first()
    if not challenge:
        return False
    # Trava do tenant impede corrida de dois aceites do mesmo e-mail.
    sub = EnrollmentSubmission.objects.select_related("tenant", "terms").get(
        pk=challenge["submission_id"],
    )
    tenant = Tenant.objects.select_for_update().get(pk=sub.tenant_id)
    submission = EnrollmentSubmission.objects.select_for_update().get(pk=sub.id)
    if (tenant.status != Tenant.Status.ACTIVE
            or submission.status != EnrollmentSubmission.Status.EMAIL_VERIFIED
            or submission.email_verified_at is None
            or submission.withdrawn_at is not None
            or submission.participant_id is not None):
        return False
    # Uma pessoa já inscrita neste mesmo tenant não vira outra por novo formulário.
    if ProgramParticipant.objects.filter(
        tenant=tenant, contact_email__iexact=submission.email,
        status__in=(ProgramParticipant.Status.ACTIVE, ProgramParticipant.Status.PAUSED),
    ).exists():
        return False
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
    attach_verified_contact(
        tenant_id=tenant.pk, participant_id=participant.pk,
        email=submission.email, proof_method="email_otp",
    )
    return True
