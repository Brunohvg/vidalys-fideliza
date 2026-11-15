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

