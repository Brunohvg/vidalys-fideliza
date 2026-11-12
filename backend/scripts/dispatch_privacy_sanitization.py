"""Reenfileirar limpeza de privacidade pendente sem dados pessoais na saída.

Dry-run por padrão; use --enqueue para despachar para o Celery. Adequado
para recuperação quando o broker esteve indisponível após o webhook.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
import django
django.setup()

from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.privacy_models import PrivacyWebhookRequest
from apps.nuvemshop.tasks import sanitize_store_after_redact
from apps.tenants.models import Tenant


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit",type=int,default=20)
    parser.add_argument("--enqueue",action="store_true")
    args=parser.parse_args()
    if not 1<=args.limit<=100:
        parser.error("--limit deve estar entre 1 e 100")
    pending=PrivacyWebhookRequest.objects.filter(
        topic=PrivacyWebhookRequest.Topic.STORE_REDACT,
        tenant__isnull=False,
        tenant__status=Tenant.Status.SUSPENDED,
        sanitized_at__isnull=True,
    ).order_by("received_at")
    ids=list(pending.values_list("id","tenant_id")[:args.limit])
    sent=blocked=failed=0
    for receipt_id,tenant_id in ids:
        if NuvemshopInstallation.objects.filter(tenant_id=tenant_id).exists():
            blocked+=1
            continue
        if args.enqueue:
            try:
                sanitize_store_after_redact.delay(str(receipt_id))
                sent+=1
            except Exception:
                failed+=1
    print("Solicitações de loja pendentes no lote:",len(ids))
    print("Aguardando desconexão:",blocked)
    print("Tarefas enfileiradas:",sent)
    print("Falhas de envio:",failed)
    print("Execução:", "reenvio solicitado" if args.enqueue else "somente consulta")
    return 2 if failed else 0


if __name__=="__main__":
    raise SystemExit(main())
