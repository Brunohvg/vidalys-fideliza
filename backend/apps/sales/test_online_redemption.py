"""Clube no site: ganhar em pedido pago, cupom único reservado, uso no site, no caixa e vencimento.

A Nuvemshop é simulada (_create_remote/_delete_remote); nada sai da máquina de teste.
"""
import hashlib
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.nuvemshop.models import NuvemshopInstallation
from apps.participants.enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms
from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent, PointLot
from apps.points.services import lot_balances
from apps.tenants.models import Tenant
from .models import CounterPilot, OnlineCoupon, ProgramMode, SaleRecord
from .online import (
    CouponPending, CouponUnavailable, free_for_counter, handle_order, issue_coupon, present_coupon,
    reconcile_coupon, refresh_tenant, site_status,
)
from .pilot import wallet_balances

FLAGS = dict(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True, FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED=True,
             FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True, FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True)
REMOTE = mock.patch("apps.sales.online._create_remote", return_value=("777", "https://loja.example/discount/X"))
DELETE = mock.patch("apps.sales.online._delete_remote", return_value=True)


def FIND(remote_id):
    return mock.patch("apps.sales.online._find_remote", return_value=remote_id)


class StoreFixture:
    """Loja Nuvemshop em giftback, clube ativo e uma cliente com e-mail confirmado (reutilizado)."""
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="online-owner")
        self.tenant = Tenant.objects.create(name="Loja Online", slug="loja-online", platform="nuvemshop",
                                            external_store_id="555", status=Tenant.Status.ACTIVE)
        NuvemshopInstallation.objects.create(tenant=self.tenant, client_id="1", store_id="555", token_ciphertext="x",
                                             scope="read_orders,write_coupons,read_customers")
        ProgramMode.objects.create(tenant=self.tenant, mode="giftback", giftback_bps=1000, giftback_cap_cents=2000,
                                   giftback_min_order_cents=8000, giftback_validity_days=30, giftback_hold_days=0,
                                   updated_by=self.owner)
        CounterPilot.objects.create(tenant=self.tenant, active=True, per_sale_cap_points=5000, updated_by=self.owner)
        now = timezone.now()
        self.ana = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Ana", contact_email="ana@example.invalid", external_customer_id=None,
            consent_at=now - timedelta(days=5), consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE)
        terms = ProgramTerms.objects.create(tenant=self.tenant, version="v1", title="Regulamento",
                                            body="Regras do clube para o teste. " * 3,
                                            privacy_notice="Dados protegidos neste teste do clube. " * 4, approved_at=now)
        invite = EnrollmentInvite.objects.create(tenant=self.tenant, terms=terms,
                                                 token_digest=hashlib.sha256(b"ana").hexdigest(),
                                                 expires_at=now + timedelta(hours=1), consumed_at=now)
        EnrollmentSubmission.objects.create(tenant=self.tenant, invitation=invite, terms=terms, name="Ana",
                                            email="Ana@Example.invalid", accepted_at=now, terms_digest="c" * 64,
                                            email_verified_at=now, participant=self.ana)

    def paid(self, order_id, cents, codes=(), email="ana@example.invalid"):
        order = {"contact_email": email, "coupon": [{"code": c} for c in codes]}
        return handle_order(tenant=self.tenant, order=order, order_id=order_id,
                            status=SaleRecord.OrderStatus.PAID, total_cents=cents)


@override_settings(**FLAGS)
class OnlineRedemptionTests(StoreFixture, TestCase):

    def test_site_status_lists_what_is_missing(self):
        self.assertTrue(site_status(self.tenant)["coupons_ready"])
        with override_settings(FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=False):
            self.assertFalse(site_status(self.tenant)["coupons_ready"])
        NuvemshopInstallation.objects.filter(tenant=self.tenant).update(scope="read_orders")
        self.assertFalse(site_status(self.tenant)["coupons_scope"])

    def test_paid_order_earns_by_verified_email_and_cancel_reverses(self):
        self.assertIn("granted", self.paid("9001", 15776))
        self.assertIn("nothing", self.paid("9001", 15776))                 # webhook repetido: idempotente
        lot = PointLot.objects.get(source_reference="site:9001")
        self.assertEqual(lot.points_issued, 1577)
        self.assertEqual(self.paid("9002", 10000, email="outra@example.invalid"), "nothing")  # fora do clube
        handle_order(tenant=self.tenant, order={}, order_id="9001",
                     status=SaleRecord.OrderStatus.REFUNDED, total_cents=15776)
        self.assertEqual(sum(lot_balances(lot).values()), 0)

    def test_coupon_reserves_credit_and_site_use_redeems(self):
        self.paid("9001", 15776)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        self.assertEqual(coupon.state, "issued")
        self.assertEqual(coupon.discount_cents, 1577)
        self.assertEqual(coupon.min_order_cents, 8000)
        self.assertTrue(coupon.code.startswith("LOJAON-"))
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)
        self.assertIn("coupon_used", self.paid("9100", 12000, codes=[coupon.code.lower()]))
        coupon.refresh_from_db()
        self.assertEqual(coupon.state, "used")
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 0)

    def test_refresh_replaces_coupon_when_new_credit_and_expires_old(self):
        self.paid("9001", 10000)                                            # R$ 10
        with REMOTE, DELETE:
            first = issue_coupon(self.ana)
            self.paid("9002", 10000)                                        # +R$ 10 liberado na hora
            out = refresh_tenant(self.tenant)
        self.assertEqual(out["replaced"], 1)
        first.refresh_from_db()
        self.assertEqual(first.state, "cancelled")
        current = OnlineCoupon.objects.get(state="issued")
        self.assertEqual(current.discount_cents, 2000)                      # um cupom só, com o total
        OnlineCoupon.objects.filter(pk=current.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with DELETE:
            self.assertEqual(refresh_tenant(self.tenant)["expired"], 1)

    def test_paused_or_missing_scope_blocks_new_coupon(self):
        self.paid("9001", 15776)
        CounterPilot.objects.filter(tenant=self.tenant).update(coupons_paused=True)
        with REMOTE, self.assertRaises(CouponUnavailable):
            issue_coupon(self.ana)

    # ---------- Resultado incerto: a reserva só volta com prova de ausência ----------

    def uncertain(self):
        """Timeout na criação: o cupom pode existir na Nuvemshop."""
        self.paid("9001", 15776)
        with mock.patch("apps.sales.online._create_remote", side_effect=TimeoutError("lost")), \
                self.assertRaises(CouponPending):
            issue_coupon(self.ana)
        return OnlineCoupon.objects.get()

    def age(self, coupon, minutes=11):
        OnlineCoupon.objects.filter(pk=coupon.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))

    def test_lost_response_keeps_reservation_and_hides_code(self):
        coupon = self.uncertain()
        self.assertEqual(coupon.state, "uncertain")
        self.assertEqual(wallet_balances(self.ana)[1], {"pending": 0, "available": 0, "reserved": 1577})
        self.assertEqual(present_coupon(coupon)["code"], "")
        self.assertEqual(coupon.audit[-1]["event"], "create_uncertain")
        with REMOTE, self.assertRaises(CouponPending):                  # clique de novo: não reserva outra vez
            issue_coupon(self.ana)
        self.assertEqual(OnlineCoupon.objects.count(), 1)

    def test_reconcile_found_on_store_becomes_issued(self):
        coupon = self.uncertain()
        with FIND("888"), mock.patch("apps.sales.online._apply_url", return_value="https://loja.example/discount/Y"):
            coupon = reconcile_coupon(coupon)
        self.assertEqual((coupon.state, coupon.remote_id), ("issued", "888"))
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)

    def test_reconcile_absent_needs_two_checks_30min_apart_and_one_hour(self):
        coupon = self.uncertain()
        with FIND(None):
            self.assertEqual(reconcile_coupon(coupon).state, "uncertain")   # pode ser atraso da Nuvemshop
        self.age(coupon, 61)
        with FIND(None):
            self.assertEqual(reconcile_coupon(coupon).state, "uncertain")   # negativas recentes demais
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)
        old = (timezone.now() - timedelta(minutes=31)).isoformat(timespec="seconds")
        coupon.refresh_from_db()
        OnlineCoupon.objects.filter(pk=coupon.pk).update(
            audit=[{**e, "at": old} if e["event"] == "absent_seen" else e for e in coupon.audit])
        with FIND(None):
            self.assertEqual(reconcile_coupon(coupon).state, "failed")
        self.assertEqual(wallet_balances(self.ana)[1], {"pending": 0, "available": 1577, "reserved": 0})

    def test_inconclusive_check_never_releases(self):
        coupon = self.uncertain()
        self.age(coupon, 120)
        with mock.patch("apps.sales.online._find_remote", side_effect=RuntimeError("503")):
            coupon = reconcile_coupon(coupon)
        self.assertEqual(coupon.state, "uncertain")
        self.assertEqual(coupon.audit[-1]["event"], "check_inconclusive")
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)

    def test_worker_restart_leaves_issuing_that_hourly_refresh_resolves(self):
        self.paid("9001", 15776)
        with mock.patch("apps.sales.online._create_remote", side_effect=SystemExit):  # processo morreu
            with self.assertRaises(SystemExit):
                issue_coupon(self.ana)
        coupon = OnlineCoupon.objects.get()
        self.assertEqual(coupon.state, "issuing")
        with FIND("999"):
            self.assertEqual(refresh_tenant(self.tenant)["confirmed"], 0)    # ainda na carência: espera
        self.age(coupon)
        with FIND("999"), mock.patch("apps.sales.online._apply_url", return_value=""):
            self.assertEqual(refresh_tenant(self.tenant)["confirmed"], 1)
        self.assertEqual(OnlineCoupon.objects.get().state, "issued")

    def test_order_paid_with_uncertain_coupon_redeems_once(self):
        coupon = self.uncertain()
        self.assertIn("coupon_used", self.paid("9100", 12000, codes=[coupon.code]))
        self.assertNotIn("coupon_used", self.paid("9100", 12000, codes=[coupon.code]))   # webhook repetido
        coupon.refresh_from_db()
        self.assertEqual((coupon.state, coupon.used_order_id), ("used", "9100"))
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 0)
        self.assertEqual(PointEvent.objects.filter(kind="redeem").aggregate(t=Sum("amount"))["t"], 1577)

    def test_counter_cannot_free_uncertain_coupon_within_grace(self):
        from .pilot import PilotBlocked
        coupon = self.uncertain()
        with FIND(None), self.assertRaises(PilotBlocked):
            free_for_counter(self.ana)
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)
        self.age(coupon)
        with FIND("555"), DELETE:                                          # existia: apaga e devolve
            free_for_counter(self.ana)
        coupon.refresh_from_db()
        self.assertEqual((coupon.state, coupon.remote_id), ("cancelled", "555"))
        self.assertEqual(wallet_balances(self.ana)[1]["available"], 1577)

    def test_coupon_used_on_site_after_counter_released_it_is_still_debited(self):
        self.paid("9001", 10000)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        with DELETE:
            free_for_counter(self.ana)                                     # caixa liberou o crédito
        self.assertEqual(wallet_balances(self.ana)[1]["available"], 1000)
        self.assertIn("coupon_used", self.paid("9200", 12000, codes=[coupon.code]))   # mas já tinha sido usado
        coupon.refresh_from_db()
        self.assertEqual(coupon.state, "used")
        self.assertEqual(coupon.audit[-1]["event"], "used_after_release")
        self.assertEqual(coupon.audit[-1]["shortfall"], "0")
        # Crédito antigo debitado (1000); o pedido 9200 gera 1200 novos, ainda pendentes.
        self.assertEqual(wallet_balances(self.ana)[1], {"pending": 1200, "available": 0, "reserved": 0})

    # ---------- Pedido desfeito depois de usar o cupom ----------

    def used_then(self, status):
        self.paid("9001", 10000)                                            # R$ 10 de crédito
        with REMOTE:
            coupon = issue_coupon(self.ana)
        self.paid("9500", 12000, codes=[coupon.code])                      # usa e ganha R$ 12 (pendente)
        out = handle_order(tenant=self.tenant, order={}, order_id="9500", status=status, total_cents=12000)
        coupon.refresh_from_db()
        return coupon, out

    def test_refunded_order_returns_used_credit_once_and_reverses_its_gain(self):
        coupon, out = self.used_then(SaleRecord.OrderStatus.REFUNDED)
        self.assertIn("credit_restored", out)
        self.assertIn("reversed", out)                                      # o ganho do pedido 9500 sai
        restored = PointLot.objects.get(source_reference=f"site-refund:{coupon.pk}")
        self.assertEqual((restored.points_issued, restored.rule_version), (1000, "pilot-vr1"))
        self.assertGreaterEqual(restored.expires_at, coupon.expires_at)
        self.assertEqual(coupon.audit[-1]["event"], "restored")
        again = handle_order(tenant=self.tenant, order={}, order_id="9500",
                             status=SaleRecord.OrderStatus.CANCELLED, total_cents=12000)
        self.assertNotIn("credit_restored", again)                          # webhook repetido / cancelado depois
        self.assertEqual(PointLot.objects.filter(source_reference__startswith="site-refund:").count(), 1)
        from .pilot import issued_points, release_due
        release_due(PointLot.objects.get(pk=restored.pk).wallet)
        self.assertEqual(wallet_balances(self.ana)[1]["available"], 1000)  # crédito de volta, liberado
        self.assertEqual(issued_points(self.tenant.pk), 1000 + 1200)        # devolução não gasta orçamento

    def test_restore_skipped_when_member_left_the_club(self):
        self.paid("9001", 10000)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        self.paid("9500", 12000, codes=[coupon.code])
        ProgramParticipant.objects.filter(pk=self.ana.pk).update(status=ProgramParticipant.Status.WITHDRAWN)
        out = handle_order(tenant=self.tenant, order={}, order_id="9500",
                           status=SaleRecord.OrderStatus.CANCELLED, total_cents=12000)
        self.assertNotIn("credit_restored", out)
        coupon.refresh_from_db()
        self.assertEqual(coupon.audit[-1]["event"], "restore_skipped")

    # ---------- Reconsulta: clube antes das paradas do motor antigo, falha nunca escondida ----------

    def nuvem_order(self, order_id, codes=(), **extra):
        return {"id": int(order_id), "status": "open", "payment_status": "paid", "currency": "BRL",
                "total": "120.00", "paid_at": "2026-11-19T12:00:00+00:00", "gateway": "pagarme",
                "contact_email": "ana@example.invalid", "contact_phone": "não é telefone",
                "coupon": [{"code": c} for c in codes], **extra}

    def event(self, order_id):
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        return OrderWebhookEvent.objects.create(tenant=self.tenant, store_id="555", order_id=order_id,
                                                topic="order/paid", dedupe_key=("k" + order_id).ljust(64, "0"))

    def test_recheck_settles_club_coupon_even_when_contacts_need_manual_review(self):
        from apps.nuvemshop.order_recheck_service import _run_club
        self.paid("9001", 10000)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        # Telefone inválido faria o motor antigo parar em "conferência manual" ANTES do clube.
        out = _run_club(event=self.event("9700"), tenant=self.tenant, order=self.nuvem_order("9700", [coupon.code]))
        self.assertIn("coupon_used", out)
        coupon.refresh_from_db()
        self.assertEqual(coupon.state, "used")
        # Etapa de baixa NUNCA concede saldo novo: isso só depois de identidade e titularidade.
        self.assertNotIn("granted", out)
        self.assertFalse(PointLot.objects.filter(source_reference="site:9700").exists())

    def test_recheck_grant_step_runs_only_after_checks_and_is_idempotent(self):
        from apps.nuvemshop.order_recheck_service import _run_club
        event, order = self.event("9750"), self.nuvem_order("9750", contact_phone="")
        self.assertEqual(_run_club(event=event, tenant=self.tenant, order=order), "nothing")      # etapa 1
        self.assertIn("granted", _run_club(event=event, tenant=self.tenant, order=order, grant=True))
        self.assertNotIn("granted", _run_club(event=event, tenant=self.tenant, order=order, grant=True))
        self.assertEqual(PointLot.objects.filter(source_reference="site:9750").count(), 1)

    def test_exhausted_club_retries_go_back_to_the_queue_hourly(self):
        from apps.nuvemshop.models import NuvemshopOrderRecheck
        from apps.nuvemshop.tasks import requeue_club_retries
        old, recent = self.event("9901"), self.event("9902")
        NuvemshopOrderRecheck.objects.create(event=old, status="club_retry",
                                             checked_at=timezone.now() - timedelta(hours=2))
        NuvemshopOrderRecheck.objects.create(event=recent, status="club_retry", checked_at=timezone.now())
        with mock.patch("apps.nuvemshop.tasks.recheck_nuvemshop_order_event.delay") as delay:
            self.assertEqual(requeue_club_retries(), 1)
        delay.assert_called_once_with(str(old.pk))
        self.assertGreater(NuvemshopOrderRecheck.objects.get(event=old).checked_at,
                           timezone.now() - timedelta(minutes=1))

    def test_recheck_voided_payment_counts_as_cancelled(self):
        from apps.nuvemshop.order_recheck_service import _run_club
        self.paid("9800", 12000)
        out = _run_club(event=self.event("9800"), tenant=self.tenant,
                        order=self.nuvem_order("9800", payment_status="voided"))
        self.assertIn("reversed", out)

    def test_recheck_club_failure_is_recorded_and_retried_not_marked_checked(self):
        from apps.nuvemshop.models import NuvemshopOrderRecheck
        from apps.nuvemshop.order_recheck_service import ClubRetry, _run_club
        event = self.event("9900")
        with mock.patch("apps.sales.online.handle_order", side_effect=RuntimeError("db down")), \
                self.assertRaises(ClubRetry):
            _run_club(event=event, tenant=self.tenant, order=self.nuvem_order("9900"))
        self.assertEqual(NuvemshopOrderRecheck.objects.get(event=event).status, "club_retry")

    def test_double_click_returns_same_coupon(self):
        self.paid("9001", 15776)
        with REMOTE:
            first = issue_coupon(self.ana)
            second = issue_coupon(self.ana)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)

    def test_results_count_purchases_return_and_discount_without_causal_claim(self):
        from .results import club_results
        self.paid("9001", 10000)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        self.paid("9002", 12000, codes=[coupon.code])                      # volta e usa o cupom
        data = club_results(self.tenant, days=30)
        self.assertEqual(data["purchases"], 2)
        self.assertEqual(data["buyers"], 1)
        self.assertEqual(data["came_back"], 1)
        self.assertEqual(data["revenue_cents"], 22000)
        self.assertEqual(data["discount_cents"], 1000)
        self.assertEqual(data["pulled_revenue_cents"], 12000)
        self.assertEqual(data["cost_bps"], 455)                             # 10,00 / 220,00
        self.assertFalse(data["causal_claim"])
        self.assertEqual(len(data["months"]), 6)
