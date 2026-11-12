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
    except Exception as exc:
        # Não serializar a exceção ou detalhes de dados/tenant no log.
        logger.warning("Limpeza de dados da loja pendente, tentativa=%s",
                       self.request.retries+1)
        raise self.retry(exc=exc) from None
