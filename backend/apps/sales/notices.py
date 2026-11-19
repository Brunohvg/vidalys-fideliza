"""Avisos automáticos do piloto: "seu saldo liberou" e "seu saldo vence em breve".

Roda de hora em hora (Celery Beat) só para lojas com o piloto ativo:
1. libera os lotes cuja carência acabou (sem depender de alguém abrir o clube);
2. avisa por e-mail, uma vez por lote e por tipo, quem tem e-mail confirmado
   e aceitou receber novidades da loja.
Sem consentimento o aviso é registrado como não enviado, para nunca disparar depois.
"""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.delivery_tracking import enqueue_email
from apps.core.models import EmailDispatch
from apps.participants.models import ProgramParticipant
from apps.points.models import PointLot, PointWallet
from apps.points.services import lot_balances
from apps.tenants.models import Tenant

from .models import CounterPilot, CreditNotice
from .pilot import RULE_PREFIX, pilot_enabled, release_due

logger = logging.getLogger(__name__)

RELEASE_WINDOW = timedelta(days=3)   # não avisa liberações antigas ao ligar o recurso
EXPIRY_WINDOW = timedelta(days=5)


def recipient(participant):
    """E-mail confirmado + aceite de novidades + participação ativa; senão None."""
    if participant.status != ProgramParticipant.Status.ACTIVE:
        return None
    enrollment = getattr(participant, "local_enrollment", None)
    if (enrollment is None or enrollment.email_verified_at is None or enrollment.withdrawn_at is not None
            or not enrollment.marketing_opt_in or not enrollment.email):
        return None
    return enrollment.email


def _pilot_lots(tenant):
    return PointLot.objects.filter(tenant=tenant, rule_version__startswith=RULE_PREFIX)


def _notify(tenant, kind, lots):
    """Agrupa por cliente, grava os avisos (únicos por lote) e enfileira um e-mail por cliente."""
    from .tasks import send_credit_notice
    by_participant = {}
    for lot in lots:
        available = lot_balances(lot)["available"]
        if available <= 0:
            continue
        by_participant.setdefault(lot.wallet.participant_id, []).append((lot, available))
    queued = 0
    for participant_id, items in by_participant.items():
        participant = ProgramParticipant.objects.select_related("local_enrollment").get(pk=participant_id)
        email = recipient(participant)
        try:
            with transaction.atomic():
                for lot, _ in items:
                    CreditNotice.objects.create(tenant=tenant, lot=lot, kind=kind, emailed=bool(email))
                if email:
                    amount = sum(value for _, value in items)
                    soonest = min(lot.expires_at for lot, _ in items)
                    enqueue_email(EmailDispatch.Kind.NOTICE, participant.pk, send_credit_notice,
                                  str(participant.pk), kind, amount, soonest.isoformat())
                    queued += 1
        except IntegrityError:
            continue  # outra execução já avisou este lote
    return queued


def scan_tenant(tenant):
    if not pilot_enabled(tenant):
        return {"released": 0, "expiring": 0}
    now = timezone.now()
    due = PointWallet.objects.filter(
        tenant=tenant, lots__rule_version__startswith=RULE_PREFIX,
        lots__unlock_at__lte=now, lots__expires_at__gt=now,
    ).distinct()
    for wallet in due:
        with transaction.atomic():
            release_due(wallet)
    released = _pilot_lots(tenant).filter(
        unlock_at__lte=now, unlock_at__gte=now - RELEASE_WINDOW, expires_at__gt=now,
    ).exclude(notices__kind=CreditNotice.Kind.RELEASED).select_related("wallet")
    expiring = _pilot_lots(tenant).filter(
        unlock_at__lte=now, expires_at__gt=now, expires_at__lte=now + EXPIRY_WINDOW,
    ).exclude(notices__kind=CreditNotice.Kind.EXPIRING).select_related("wallet")
    result = {"released": _notify(tenant, CreditNotice.Kind.RELEASED, released),
              "expiring": _notify(tenant, CreditNotice.Kind.EXPIRING, expiring)}
    logger.info("pilot_notices tenant=%s released=%s expiring=%s", tenant.pk, result["released"], result["expiring"])
    return result


def scan_all():
    tenants = Tenant.objects.filter(
        pk__in=CounterPilot.objects.filter(active=True).values("tenant_id"), status=Tenant.Status.ACTIVE)
    return {str(tenant.pk): scan_tenant(tenant) for tenant in tenants}
