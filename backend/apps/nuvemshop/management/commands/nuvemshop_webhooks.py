"""Confere (e com --ensure cadastra) os avisos de pedido de uma loja Nuvemshop.

    python manage.py nuvemshop_webhooks --tenant <slug>            # só confere
    python manage.py nuvemshop_webhooks --tenant <slug> --ensure   # cria o que faltar

Lojas conectadas antes do cadastro automático: rode uma vez com --ensure (ou clique em
"Atualizar conexão" em Configurações → Canais). Não apaga avisos existentes.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Tenant

LABELS = {"ok": "já cadastrado", "created": "cadastrado agora", "missing": "FALTANDO (rode com --ensure)"}
SKIPPED = {"receiver_off": "Receptor de avisos desligado (FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=0).",
           "no_order_scope": "A loja não autorizou a leitura de pedidos. Atualize a conexão aceitando Pedidos."}


class Command(BaseCommand):
    help = "Confere ou cadastra os avisos de pedido (order/paid e order/updated) na Nuvemshop."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--ensure", action="store_true")

    def handle(self, *args, **opts):
        from apps.nuvemshop.webhook_setup import order_webhooks
        tenant = Tenant.objects.filter(slug=opts["tenant"], platform="nuvemshop").first()
        if tenant is None:
            raise CommandError("Loja Nuvemshop não encontrada.")
        try:
            result = order_webhooks(tenant, ensure=opts["ensure"])
        except Exception as exc:
            raise CommandError(f"Não foi possível falar com a Nuvemshop: {exc}") from None
        if "_skipped" in result:
            raise CommandError(SKIPPED.get(result["_skipped"], result["_skipped"]))
        for event, state in sorted(result.items()):
            self.stdout.write(f"{'✔' if state != 'missing' else '✖'} {event}: {LABELS[state]}")
        if "missing" in result.values():
            raise SystemExit(1)
