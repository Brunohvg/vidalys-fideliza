"""Celery Beat: reativação sem notificação ou escrita financeira automática."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant

from .models import LoyaltyEngagement, LoyaltyGrant, LoyaltyRule
from .services import LoyaltyBlocked, release_grant


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
