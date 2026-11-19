"""Processamento idempotente de limpeza de loja desinstalada.

Somente UUID de protocolo trafega no broker, nunca PII ou tokens da loja.
Falha é reprocessável pelo banco/outbox e não aciona APIs externas.
"""
import logging
from celery import shared_task
from .privacy_erasure import sanitize_store_privacy

logger=logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_jitter=True,
             retry_backoff_max=900, acks_late=True, ignore_result=True)
def sanitize_store_after_redact(self, receipt_id: str):
    try:
        return sanitize_store_privacy(receipt_id)
    except Exception:
        # Não serializar a exceção ou detalhes de dados/tenant no log.
        logger.warning("Limpeza de dados da loja pendente, tentativa=%s",
                       self.request.retries+1)
        raise self.retry(exc=RuntimeError("privacy_cleanup_failed")) from None


@shared_task(bind=True, name="nuvemshop.recheck_order",
             queue="nuvemshop", max_retries=5, retry_backoff=True,
             retry_jitter=True, retry_backoff_max=600,
             acks_late=True, ignore_result=True)
def recheck_nuvemshop_order_event(self, event_id: str):
    """Reconsulta HMAC inbox sob OAuth, somente no worker isolado."""
    from apps.channels.services import IngestionConflict
    from .coupon_revocation import RevocationBlocked
    from .order_recheck_service import ClubRetry, RecheckBlocked, recheck_order_event
    from .order_readonly import OrderReadError
    from .security import OAuthConfigurationError
    try:
        return recheck_order_event(event_id=event_id)
    except (RecheckBlocked, IngestionConflict, RevocationBlocked):
        # Conflito permanente: registrar para conciliação manual; não
        # produzir loop de retries nem divulgar PII/token em logs.
        logger.warning("Pedido Nuvemshop exige conciliacao manual")
        return "requires_review"
    except (OrderReadError, OAuthConfigurationError, ClubRetry):
        logger.warning("Reconsulta OAuth temporariamente indisponivel, tentativa=%s",
                       self.request.retries + 1)
        raise self.retry(exc=RuntimeError("nuvemshop_order_recheck_retry")) from None



@shared_task(bind=True, name="nuvemshop.revoke_expired_coupons",
             queue="nuvemshop", max_retries=2, retry_backoff=True,
             retry_jitter=True, acks_late=True, ignore_result=True)
def revoke_expired_nuvemshop_coupons(self):
    """Bounded expiration scan: no automatic store mutation unless all gates pass."""
    from django.conf import settings
    from django.utils import timezone
    from .coupon_revocation import revoke_and_release, RevocationBlocked
    from .models import NuvemshopCouponIntent
    if not (
        settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
        and settings.FIDELIZA_POINTS_WRITES_ENABLED
        and settings.FIDELIZA_LEDGER_WRITES_ENABLED
        and settings.FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED
    ):
        return "financial_gates_off"
    candidates = list(NuvemshopCouponIntent.objects.filter(
        tenant__loyalty_live_enabled=True,
        state__in=(NuvemshopCouponIntent.State.ISSUED,
                   NuvemshopCouponIntent.State.REVOKING),
        order_id="", voucher__expires_at__lte=timezone.now(),
    ).order_by("created_at").values_list("pk",flat=True)[:20])
    completed = 0
    for identifier in candidates:
        try:
            _, changed = revoke_and_release(intent_id=identifier, reason="expired")
            completed += int(changed)
        except RevocationBlocked:
            # No free balance on failure. Next scan or operator inspects it.
            logger.warning("Revogação automática de cupom requer revisão")
    return f"checked={len(candidates)} revoked={completed}"


@shared_task(bind=True, name="nuvemshop.ensure_order_webhooks",
             queue="nuvemshop", max_retries=4, retry_backoff=True,
             retry_jitter=True, retry_backoff_max=900, acks_late=True, ignore_result=True)
def ensure_order_webhooks(self, tenant_id: str):
    """Depois do OAuth: cadastra os avisos de pedido que faltam. Só o UUID trafega no broker."""
    from apps.tenants.models import Tenant
    from .webhook_setup import order_webhooks
    tenant = Tenant.objects.filter(pk=tenant_id, platform="nuvemshop").first()
    if tenant is None:
        return
    try:
        order_webhooks(tenant, ensure=True)
    except Exception:
        logger.warning("Avisos de pedido pendentes de cadastro, tentativa=%s", self.request.retries + 1)
        raise self.retry(exc=RuntimeError("order_webhooks_pending")) from None


CLUB_RETRY_AFTER_MINUTES = 60
CLUB_RETRY_BATCH = 50


def requeue_club_retries(now=None):
    """Pedidos com status club_retry parados há 1 h+ voltam para a reconsulta (de hora em hora,
    sem limite de dias): a baixa do clube não pode ficar perdida depois que o Celery desiste.
    Visíveis no club_readiness enquanto não resolverem. Só UUIDs trafegam no broker."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import NuvemshopOrderRecheck
    now = now or timezone.now()
    stale = (NuvemshopOrderRecheck.objects
             .filter(status="club_retry", checked_at__lte=now - timedelta(minutes=CLUB_RETRY_AFTER_MINUTES))
             .order_by("checked_at").values_list("event_id", flat=True)[:CLUB_RETRY_BATCH])
    count = 0
    for event_id in stale:
        NuvemshopOrderRecheck.objects.filter(event_id=event_id, status="club_retry").update(checked_at=now)
        recheck_nuvemshop_order_event.delay(str(event_id))
        count += 1
    if count:
        logger.warning("Pedidos do clube devolvidos para reconsulta: %s", count)
    return count
