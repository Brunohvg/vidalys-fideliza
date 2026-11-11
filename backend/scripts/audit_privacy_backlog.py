"""Auditoria resumida de pendências LGPD, sem PII.

Uso: python scripts/audit_privacy_backlog.py --hours 24
Retorna exit=2 se há solicitações atrasadas; adequado para monitor interno.
"""
import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.db.models import Count
from django.utils import timezone
from apps.nuvemshop.privacy_models import PrivacyWebhookRequest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours",type=int,default=24)
    args=parser.parse_args()
    if not 1 <= args.hours <= 720:
        parser.error("--hours entre 1 e 720")
    threshold=timezone.now()-timedelta(hours=args.hours)
    waiting=PrivacyWebhookRequest.objects.exclude(
        state=PrivacyWebhookRequest.State.COMPLETED
    )
    counts=list(waiting.values("topic","state").annotate(total=Count("id")).order_by("topic","state"))
    old=waiting.filter(received_at__lt=threshold).count()
    print("SOLICITACOES_PRIVACIDADE_PENDENTES:",waiting.count())
    for item in counts:
        print(f"  {item['topic']} {item['state']}: {item['total']}")
    print(f"PENDENTES_HA_MAIS_DE_{args.hours}H:",old)
    print("RELATORIOS_ENVIADOS_OU_EXCLUSOES_CONCLUIDAS_NAO_SAO_PRESUMIDOS")
    return 2 if old else 0


if __name__=="__main__":
    raise SystemExit(main())
