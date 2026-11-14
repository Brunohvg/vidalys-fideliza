"""Celery Beat: reativação sem notificação ou escrita financeira automática."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.customers.models import CustomerProfile
from apps.tenants.models import Tenant

from .models import FinancialEvidence, LoyaltyEngagement, LoyaltyGrant, LoyaltyRule
from .services import LoyaltyBlocked, record_engagement_eligibility, release_grant, reverse_grant


@shared_task(name="loyalty.scan_winback", ignore_result=True)
def scan_winback():
    if not getattr(settings, "FIDELIZA_LOYALTY_ENGAGEMENT_SCAN_ENABLED", False):
        return {"skipped": True, "created": 0}
    now = timezone.now()
    period = now.strftime("%Y-%m")
    created = 0
    for rule in LoyaltyRule.objects.filter(
        enabled=True, tenant__status=Tenant.Status.ACTIVE,
    ).select_related("tenant").iterator():
        cutoff = now - timedelta(days=rule.winback_after_days)
        prior = (LoyaltyGrant.objects.filter(
            tenant=rule.tenant,
            status__in=(LoyaltyGrant.Status.PENDING, LoyaltyGrant.Status.RELEASED),
        ).values("participant_id").annotate(last_capture=Max("captured_at")))
        inactive = [r["participant_id"] for r in prior if r["last_capture"] < cutoff]
        for participant in ProgramParticipant.objects.filter(
            tenant=rule.tenant, status=ProgramParticipant.Status.ACTIVE,
            pk__in=inactive, customer_profile__isnull=False,
            customer_profile__verified_contacts__isnull=False,
        ).distinct().iterator():
            _, was_created = LoyaltyEngagement.objects.get_or_create(
                tenant=rule.tenant, participant=participant,
                kind=LoyaltyEngagement.Kind.WINBACK, period_key=period,
                defaults={"eligible_at": now},
            )
            created += int(was_created)
    # "eligible" NÃO significa campanha disparada, voucher ou pontos emitidos.
    return {"skipped": False, "created": created, "notifications_sent": 0}


@shared_task(name="loyalty.release_due_grants", ignore_result=True)
def release_due_grants():
    if not (
        getattr(settings, "FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED", False)
        and getattr(settings, "FIDELIZA_POINTS_WRITES_ENABLED", False)
        and getattr(settings, "FIDELIZA_LEDGER_WRITES_ENABLED", False)
    ):
        return {"skipped": True, "released": 0}
    now = timezone.now()
    released = 0
    ids = LoyaltyGrant.objects.filter(
        status=LoyaltyGrant.Status.PENDING,
        unlock_at__lte=now, expires_at__gt=now,
        sale__order_status="paid",
    ).values_list("pk", flat=True)[:200]
    for pk in ids:
        try:
            _, changed = release_grant(grant_id=pk)
            released += int(changed)
        except (LoyaltyBlocked, PermissionError):
            # A conciliação operacional deve analisar a pendência.
            continue
    return {"skipped": False, "released": released}



@shared_task(name="loyalty.reconcile_verified_refunds", ignore_result=True)
def reconcile_verified_refunds():
    """Inverte somente compras com comprovante PSP normalizado e aprovado."""
    if not (
        getattr(settings, "FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED", False)
        and getattr(settings, "FIDELIZA_POINTS_WRITES_ENABLED", False)
        and getattr(settings, "FIDELIZA_LEDGER_WRITES_ENABLED", False)
    ):
        return {"skipped": True, "reversed": 0, "pending_review": 0}
    trusted = getattr(settings, "FIDELIZA_TRUSTED_PAYMENT_ADAPTERS", frozenset())
    if not trusted:
        return {"skipped": True, "reversed": 0, "pending_review": 0}
    candidates = LoyaltyGrant.objects.filter(
        status__in=[LoyaltyGrant.Status.PENDING, LoyaltyGrant.Status.RELEASED],
        sale__order_status__in=["cancelled", "refunded"],
    ).values_list("pk", "sale_id")[:200]
    reversed_count = 0
    review_count = 0
    for grant_id, sale_id in candidates:
        proof = FinancialEvidence.objects.filter(
            sale_id=sale_id, kind=FinancialEvidence.Kind.REFUND,
            provider__in=trusted,
        ).order_by("created_at", "pk").first()
        if proof is None:
            review_count += 1
            continue
        try:
            _, changed = reverse_grant(
                grant_id=grant_id, refund_evidence_id=proof.pk,
            )
            reversed_count += int(changed)
        except (LoyaltyBlocked, PermissionError):
            review_count += 1
    return {"skipped": False, "reversed": reversed_count, "pending_review": review_count}



@shared_task(name="loyalty.scan_verified_birthdays", ignore_result=True)
def scan_verified_birthdays():
    """Somente elegibilidade anual; NÃO envia campanha nem cria pontos."""
    if not getattr(settings, "FIDELIZA_LOYALTY_ENGAGEMENT_SCAN_ENABLED", False):
        return {"skipped": True, "created": 0, "notifications_sent": 0}
    now = timezone.now()
    created = 0
    candidates = CustomerProfile.objects.filter(
        tenant__status=Tenant.Status.ACTIVE,
        participant__status=ProgramParticipant.Status.ACTIVE,
        birth_date__month=now.month, birth_date__day=now.day,
        birth_date_verified_at__isnull=False,
        birth_date_consent_at__isnull=False,
    ).values_list("participant_id", flat=True)[:500]
    for participant_id in candidates:
        try:
            _, added = record_engagement_eligibility(
                participant_id=participant_id,
                kind=LoyaltyEngagement.Kind.BIRTHDAY,
                now=now,
            )
            created += int(added)
        except (LoyaltyBlocked, ProgramParticipant.DoesNotExist):
            continue
    return {"skipped": False, "created": created, "notifications_sent": 0}
