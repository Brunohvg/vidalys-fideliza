"""Atestado de prontidão do clube, SOMENTE LEITURA. Evidência para o deploy e o teste real.

Uso no servidor (Coolify → serviço api → Terminal):
    python manage.py club_readiness                 # todas as lojas com clube
    python manage.py club_readiness --tenant <slug> # uma loja

Mostra versão, migrações pendentes, chaves do servidor, Redis e workers (inclui a fila
"nuvemshop"), e por loja: modo, tetos, bloqueios, o que falta no site, últimos pedidos
recebidos e cupons por estado. Só contagens e datas: sem nomes, e-mails, tokens ou valores
de clientes. Sai com código 1 se houver falha crítica.
"""
import os
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count
from django.utils import timezone

OK, FAIL, WARN = "✔", "✖", "!"
FLAGS = (
    ("FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", "Leitura de pedidos"),
    ("FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", "Avisos de pedido (webhooks)"),
    ("FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED", "Reconsulta do pedido pago"),
    ("FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED", "Criação de cupons"),
    ("FIDELIZA_EMAIL_DELIVERY_ENABLED", "Envio de e-mails"),
)
ROUTINES = ("sales.online_coupon_refresh", "sales.pilot_wallet_scan")


class Command(BaseCommand):
    help = "Confere, sem alterar nada, se o clube está pronto para operar (deploy e teste real)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="slug de uma loja")
        parser.add_argument("--skip-workers", action="store_true", help="não consultar Redis, workers nem Nuvemshop")

    def line(self, mark, text):
        self.stdout.write(f"  {mark} {text}")
        if mark == FAIL:
            self.failed = True

    def handle(self, *args, **opts):
        self.failed = False
        now = timezone.now()
        self.stdout.write("Vidalys Fideliza — prontidão do clube " + timezone.localtime(now).strftime("%d/%m/%Y %H:%M"))

        self.stdout.write("\nServidor")
        commit = os.getenv("SOURCE_COMMIT", "").strip()
        self.line(OK if commit else WARN, f"Versão implantada: {commit[:12] if commit else 'não informada (SOURCE_COMMIT)'}")
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            names = ", ".join(f"{m.app_label}.{m.name}" for m, _ in plan[:8])
            self.line(FAIL, f"Migrações pendentes ({len(plan)}): {names}")
        else:
            self.line(OK, "Banco com todas as migrações aplicadas")
        for key, label in FLAGS:
            on = bool(getattr(settings, key, False))
            self.line(OK if on else WARN, f"{label}: {'ligado' if on else 'desligado'} neste serviço ({key})")
        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        tasks = {item.get("task") for item in schedule.values()}
        for routine in ROUTINES:
            self.line(OK if routine in tasks else FAIL, f"Rotina agendada: {routine}")
        if not opts["skip_workers"]:
            self.workers()

        from apps.sales.models import CounterPilot
        pilots = CounterPilot.objects.select_related("tenant").order_by("tenant__slug")
        if opts["tenant"]:
            pilots = pilots.filter(tenant__slug=opts["tenant"])
        if not pilots.exists():
            self.stdout.write("\nNenhuma loja com clube configurado" + (f" ({opts['tenant']})" if opts["tenant"] else "") + ".")
        for pilot in pilots:
            self.store(pilot, now, remote=not opts["skip_workers"])

        self.stdout.write("\nResultado: " + ("FALHA — corrija os itens ✖" if self.failed else "OK (itens ! são avisos)"))
        if self.failed:
            raise SystemExit(1)

    def workers(self):
        try:
            from config.celery import app
            with app.connection_for_write() as conn:
                conn.ensure_connection(max_retries=1, timeout=3)
            self.line(OK, "Redis (fila de tarefas) respondendo")
        except Exception:
            self.line(FAIL, "Redis (fila de tarefas) não respondeu")
            return
        try:
            queues = app.control.inspect(timeout=3).active_queues() or {}
        except Exception:
            queues = {}
        if not queues:
            self.line(FAIL, "Nenhum worker respondeu (api/worker/nuvemshop-sync parados?)")
            return
        names = {q.get("name") for items in queues.values() for q in items}
        self.line(OK, f"Workers ativos: {len(queues)}")
        self.line(OK if "nuvemshop" in names else FAIL, "Worker da fila nuvemshop (cupons e reconsulta)")

    def webhooks(self, tenant):
        """Avisos de pedido cadastrados na Nuvemshop (só leitura)."""
        from apps.nuvemshop.webhook_setup import order_webhooks
        try:
            result = order_webhooks(tenant)
        except Exception:
            self.line(WARN, "Avisos cadastrados na Nuvemshop: não verificado (sem resposta)")
            return
        if "_skipped" in result:
            self.line(WARN, f"Avisos cadastrados na Nuvemshop: não verificado ({result['_skipped']})")
            return
        for event, state in sorted(result.items()):
            self.line(OK if state == "ok" else FAIL, f"Aviso {event} cadastrado na Nuvemshop" if state == "ok"
                      else f"Aviso {event} NÃO cadastrado: python manage.py nuvemshop_webhooks --tenant {tenant.slug} --ensure")

    def store(self, pilot, now, remote=True):
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        from apps.points.models import PointLot
        from apps.sales.models import OnlineCoupon
        from apps.sales.online import site_status
        from apps.sales.policy import blockers, can_operate, effective_budget, effective_per_sale, mode_of
        tenant = pilot.tenant
        brl = lambda cents: ("R$ " + f"{cents / 100:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
        self.stdout.write(f"\nLoja {tenant.slug} ({tenant.platform}, {tenant.status})")
        mode = "comercial" if mode_of(pilot) == "commercial" else "teste"
        self.line(OK if pilot.active else WARN, f"Clube {'ativo' if pilot.active else 'pausado'} · modo {mode}")
        self.line(OK, f"Tetos em vigor: {brl(effective_per_sale(pilot))} por compra · {brl(effective_budget(pilot))} no total")
        for text in blockers(pilot):
            self.line(FAIL, f"Bloqueio do comercial: {text}")
        self.line(OK if can_operate(tenant) else WARN, "Balcão pode gerar saldo agora" if can_operate(tenant)
                  else "Balcão não gera saldo agora (pausado ou bloqueado)")
        if tenant.platform == "nuvemshop":
            status = site_status(tenant)
            labels = (("connected", "Loja conectada"), ("orders_scope", "Permissão de pedidos"),
                      ("coupons_scope", "Permissão de cupons (write_coupons)"), ("webhooks", "Avisos de pedido ligados"),
                      ("coupons_server", "Cupons ligados no servidor"))
            for key, label in labels:
                self.line(OK if status[key] else WARN, label)
            if remote:
                self.webhooks(tenant)
            since = now - timedelta(days=7)
            events = OrderWebhookEvent.objects.filter(tenant=tenant)
            last = events.order_by("-received_at").values_list("received_at", flat=True).first()
            self.line(OK if last else WARN, "Último aviso de pedido: " +
                      (timezone.localtime(last).strftime("%d/%m %H:%M") if last else "nenhum recebido ainda"))
            self.line(OK, f"Avisos de pedido nos últimos 7 dias: {events.filter(received_at__gte=since).count()}")
            by_state = dict(OnlineCoupon.objects.filter(tenant=tenant).values_list("state").annotate(n=Count("id")))
            summary = ", ".join(f"{state} {n}" for state, n in sorted(by_state.items())) or "nenhum"
            self.line(OK, f"Cupons por estado: {summary}")
            stuck = OnlineCoupon.objects.filter(
                tenant=tenant, state__in=("issuing", "uncertain"), created_at__lte=now - timedelta(hours=1)).count()
            self.line(WARN if stuck else OK, f"Cupons em confirmação há mais de 1 hora: {stuck}")
            site_lots = PointLot.objects.filter(tenant=tenant, source_reference__startswith="site:",
                                                created_at__gte=since).count()
            self.line(OK, f"Compras do site que geraram saldo (7 dias): {site_lots}")
        counter_lots = PointLot.objects.filter(tenant=tenant, source_reference__startswith="counter:",
                                               created_at__gte=now - timedelta(days=7)).count()
        self.line(OK, f"Vendas de balcão que geraram saldo (7 dias): {counter_lots}")
