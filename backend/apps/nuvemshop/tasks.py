"""Processamento idempotente de limpeza de loja desinstalada.

Somente UUID de protocolo trafega no broker, nunca PII ou tokens da loja.
Falha é reprocessável pelo banco/outbox e não aciona APIs externas.
"""
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
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
    from .order_recheck_service import RecheckBlocked, recheck_order_event
    from .order_readonly import OrderReadError
    from .security import OAuthConfigurationError
    try:
        return recheck_order_event(event_id=event_id)
    except (RecheckBlocked, IngestionConflict):
        # Conflito permanente: registrar para conciliação manual; não
        # produzir loop de retries nem divulgar PII/token em logs.
        logger.warning("Pedido Nuvemshop exige conciliacao manual")
        return "requires_review"
    except (OrderReadError, OAuthConfigurationError):
        logger.warning("Reconsulta OAuth temporariamente indisponivel, tentativa=%s",
                       self.request.retries + 1)
        raise self.retry(exc=RuntimeError("nuvemshop_order_recheck_retry")) from None



@shared_task(bind=True, name="nuvemshop.revoke_coupon",
             queue="nuvemshop", max_retries=4, retry_backoff=True,
             retry_jitter=True, retry_backoff_max=900,
             acks_late=True, ignore_result=True)
def revoke_nuvemshop_coupon(self, intent_id: str, reason: str):
    from .coupon_revocation import CouponRevokeBlocked, revoke_coupon
    try:
        _, released = revoke_coupon(intent_id=intent_id, reason=reason)
        return "revoked_and_released" if released else "revoked_funds_held"
    except CouponRevokeBlocked:
        # Resultado incerto: a transação continua congelada. Um recheck
        # só faz GET antes de qualquer repetição de DELETE.
        logger.warning("Revogacao de cupom exige conciliação no provedor")
        return "needs_review"


@shared_task(name="nuvemshop.scan_expired_coupons",
             queue="nuvemshop", ignore_result=True)
def scan_expired_nuvemshop_coupons():
    """Beat exclusivo: no máximo 25 intents, carência de 30min por padrão."""
    from datetime import timedelta
    from .models import NuvemshopCouponIntent
    if not getattr(settings, "FIDELIZA_NUVEMSHOP_COUPON_REVOCATION_ENABLED", False):
        return 0
    now = timezone.now()
    ids = list(NuvemshopCouponIntent.objects.filter(
        voucher__expires_at__lte=now-timedelta(minutes=30),
        order_id="",
        state__in=[NuvemshopCouponIntent.State.ISSUED],
    ).order_by("created_at").values_list("pk", flat=True)[:25])
    for intent_id in ids:
        revoke_nuvemshop_coupon.delay(str(intent_id), "expired")
    return len(ids)
