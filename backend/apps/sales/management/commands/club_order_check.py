"""Por que um pedido do site gerou (ou não) saldo no clube? SOMENTE LEITURA, sem dados pessoais.

    python manage.py club_order_check --tenant <slug> --number <nº do pedido na Nuvemshop>

Relê o pedido pela API (OAuth) e responde cada condição da concessão com ✔/✖: pago, avisos
recebidos e reconsulta, e-mail do pedido x cadastro confirmado no clube, celular, clube
ligado para o site, lote criado e cupons do clube no pedido. Nunca imprime e-mail, nome,
telefone, CPF ou token.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Tenant

OK, FAIL, INFO = "✔", "✖", "·"


class Command(BaseCommand):
    help = "Explica, sem dados pessoais, por que um pedido do site gerou ou não saldo no clube."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--number", required=True, help="número do pedido como aparece na Nuvemshop (#14185)")

    def line(self, mark, text):
        self.stdout.write(f"  {mark} {text}")

    def handle(self, *args, **opts):
        from apps.nuvemshop.models import NuvemshopInstallation
        from apps.nuvemshop.order_readonly import INTEGRATION_FIELDS, read_order, read_order_by_number
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        from apps.nuvemshop.security import config, decrypt_token
        from apps.participants.enrollment_models import EnrollmentSubmission
        from apps.participants.models import ProgramParticipant
        from apps.points.models import PointLot
        from apps.sales.models import CounterPilot, OnlineCoupon
        from apps.sales.online import _order_codes, _participant_for, club_buyer
        from apps.sales.policy import can_operate

        tenant = Tenant.objects.filter(slug=opts["tenant"], platform="nuvemshop").first()
        if tenant is None:
            raise CommandError("Loja Nuvemshop não encontrada.")
        number = opts["number"].lstrip("#").strip()
        cfg = config()
        installed = NuvemshopInstallation.objects.get(tenant=tenant, client_id=cfg.client_id)
        token = decrypt_token(installed.token_ciphertext, cfg.token_keys)
        try:
            found = read_order_by_number(store_id=installed.store_id, number=number,
                                         access_token=token, user_agent=cfg.user_agent)
            order_id = str(found.get("id") if isinstance(found, dict) else found)
            order = read_order(store_id=installed.store_id, order_id=order_id, access_token=token,
                               user_agent=cfg.user_agent, fields=INTEGRATION_FIELDS)
        except Exception as exc:
            raise CommandError(f"Não foi possível ler o pedido na Nuvemshop: {type(exc).__name__}") from None

        self.stdout.write(f"Pedido #{number} (id interno {order_id}) — loja {tenant.slug}")
        paid = order.get("payment_status") == "paid" and order.get("status") != "cancelled"
        self.line(OK if paid else FAIL, f"Situação: {order.get('status')} / pagamento {order.get('payment_status')}")

        events = OrderWebhookEvent.objects.filter(tenant=tenant, order_id=order_id).order_by("received_at")
        self.line(OK if events.exists() else FAIL, f"Avisos recebidos para este pedido: {events.count()}")
        for event in events:
            recheck = getattr(event, "order_recheck", None)
            self.line(INFO, f"{event.topic} às {event.received_at:%d/%m %H:%M} UTC → reconsulta: "
                            f"{recheck.status if recheck else 'não registrada'}")

        customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
        emails = {e.strip().lower() for e in (order.get("contact_email"), customer.get("email"))
                  if isinstance(e, str) and "@" in e}
        self.line(OK if len(emails) == 1 else FAIL, f"E-mails distintos no pedido: {len(emails)} (precisa ser 1)")
        if len(emails) == 1:
            email = next(iter(emails))
            subs = EnrollmentSubmission.objects.filter(tenant=tenant, email__iexact=email)
            self.line(OK if subs.exists() else FAIL, f"Cadastro no clube com o e-mail do pedido: {subs.count()}")
            verified = subs.filter(email_verified_at__isnull=False, withdrawn_at__isnull=True)
            self.line(OK if verified.exists() else FAIL, f"…com e-mail confirmado e sem saída do clube: {verified.count()}")
            active = verified.filter(participant__status=ProgramParticipant.Status.ACTIVE)
            self.line(OK if active.count() == 1 else FAIL, f"…com participação ativa: {active.count()} (precisa ser 1)")
        participant = _participant_for(tenant, order, None)
        buyer, why = club_buyer(tenant, order, participant)
        reasons = {"ok": "cliente reconhecida", "not_member": "não reconhecida como cliente do clube",
                   "phone_conflict": "celular do pedido diferente do cadastrado no clube"}
        self.line(OK if buyer else FAIL, f"Identidade do clube: {reasons.get(why, why)}")

        pilot = CounterPilot.objects.filter(tenant=tenant).first()
        self.line(OK if pilot and pilot.online_earning else FAIL, "Opção 'compras pagas no site geram saldo' ligada")
        self.line(OK if can_operate(tenant, "site_earn") else FAIL, "Clube pode gerar saldo do site agora")
        lot = PointLot.objects.filter(tenant=tenant, source_reference=f"site:{order_id}").first()
        self.line(OK if lot else FAIL, f"Saldo gerado para o pedido: {lot.points_issued if lot else 0}")
        codes = _order_codes(order)
        ours = OnlineCoupon.objects.filter(tenant=tenant, code__in=codes)
        self.line(INFO, f"Cupons no pedido: {len(codes)} · do clube: {ours.count()} "
                        f"({', '.join(sorted(c.state for c in ours)) or '—'})")
