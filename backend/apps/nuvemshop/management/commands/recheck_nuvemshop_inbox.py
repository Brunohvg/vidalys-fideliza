"""Execução controlada da inbox OAuth no container API (possui segredos OAuth).

Exemplo no Coolify Exec de homolog (nunca no worker SMTP):
  python manage.py recheck_nuvemshop_inbox --tenant-id UUID --limit 10 --apply-qa
A execução precisa de aprovação explícita por secret manager.
"""
import os
import uuid
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from apps.nuvemshop.order_recheck_service import RecheckBlocked, recheck_order_event
from apps.nuvemshop.order_readonly import OrderReadError
from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Reconsulta OAuth de notificações QA sem credenciais no worker genérico."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", required=True)
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--apply-qa", action="store_true")

    def handle(self, *args, **opts):
        if os.getenv("FIDELIZA_ENVIRONMENT") != "homolog":
            raise CommandError("Executar exclusivamente em homologação")
        if not opts["apply_qa"] or os.getenv(
            "FIDELIZA_NUVEMSHOP_RECHECK_APPROVED"
        ) != "YES_QA_REREAD":
            raise CommandError("Leitura/normalização QA não autorizada")
        if not (settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED
                and settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED
                and settings.FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED):
            raise CommandError("Gates OAuth da reconsulta desativados")
        if opts["limit"] < 1 or opts["limit"] > 30:
            raise CommandError("Limite precisa estar entre 1 e 30")
        try:
            tid = uuid.UUID(opts["tenant_id"])
        except (TypeError, ValueError):
            raise CommandError("Tenant UUID inválido") from None
        tenant = Tenant.objects.filter(pk=tid, status=Tenant.Status.ACTIVE).first()
        if tenant is None or not (tenant.slug.startswith("qa-")
                                   or tenant.slug.startswith("homolog-")):
            raise CommandError("Somente tenant QA explicitamente autorizado")
        if "bibel" in tenant.name.casefold():
            raise CommandError("Não executar em loja comercial")
        from apps.nuvemshop.models import NuvemshopOrderRecheck
        checked = NuvemshopOrderRecheck.objects.filter(
            event_id__in=OrderWebhookEvent.objects.filter(
                tenant=tenant,
            ).values_list("pk", flat=True),
            status="checked",
        ).values_list("event_id", flat=True)
        ids = list(OrderWebhookEvent.objects.filter(
            tenant=tenant,
        ).exclude(pk__in=checked).order_by("received_at").values_list(
            "pk", flat=True
        )[:opts["limit"]])
        good = 0
        review = 0
        for event_id in ids:
            try:
                recheck_order_event(event_id=event_id)
            except (RecheckBlocked, OrderReadError):
                review += 1
                continue
            good += 1
        self.stdout.write(
            f"QA_ORDER_RECHECK completed={good} review={review} processed={len(ids)} "
            "financial_settlement=OFF"
        )
