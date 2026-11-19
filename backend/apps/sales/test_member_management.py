"""Gestão de clientes e vendas pelo painel + reconhecimento e crédito retroativo no site.

Cadastro manual, remoção de cliente (LGPD), remoção de venda de balcão, reconhecimento pelo
cliente da Nuvemshop, crédito desde a adesão e ativação sem pendência. Nuvemshop simulada.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.enrollment_models import EnrollmentSubmission
from apps.participants.models import ProgramParticipant
from apps.points.models import PointLot
from apps.tenants.models import Tenant, TenantMembership
from .models import CounterPilot, CounterRedemption, OnlineCoupon, SaleRecord
from .online import credit_since_join, handle_order, issue_coupon
from .pilot import release_due, reserve_credit, wallet_balances
from .test_online_redemption import DELETE, FLAGS, REMOTE, StoreFixture


@override_settings(**FLAGS)
class MemberManagementTests(StoreFixture, TestCase):
    def setUp(self):
        super().setUp()
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        self.api = APIClient()
        self.api.force_login(self.owner)

    def post(self, name, data, **kw):
        return self.api.post(reverse(name, kwargs={"tenant_id": self.tenant.id, **kw}), data, format="json")

    def balances(self):
        return wallet_balances(self.ana)[1]

    # ---------- Cadastro manual ----------

    def test_manual_registration_needs_authorization_and_blocks_duplicates(self):
        self.assertEqual(self.post("tenant-participant-create",
                                   {"name": "Bia Lima", "email": "bia@example.invalid"}).status_code, 400)
        made = self.post("tenant-participant-create", {"name": "Bia Lima", "email": "Bia@Example.invalid",
                                                       "phone": "(31) 98888-7777", "authorized": True})
        self.assertEqual(made.status_code, 201, made.data)
        bia = ProgramParticipant.objects.get(contact_email="bia@example.invalid")
        self.assertEqual((bia.status, bia.consent_channel), ("active", "merchant_assisted"))
        self.assertEqual(bia.phone_last4, "7777")
        again = self.post("tenant-participant-create", {"name": "Bia", "email": "bia@example.invalid", "authorized": True})
        self.assertEqual(again.status_code, 409)
        # Site só conta depois de a própria cliente confirmar o e-mail.
        self.assertEqual(self.paid("9801", 10000, email="bia@example.invalid"), "nothing")
        EnrollmentSubmission.objects.filter(participant=bia).update(email_verified_at=timezone.now())
        self.assertIn("granted", self.paid("9802", 10000, email="bia@example.invalid"))

    # ---------- Remover cliente ----------

    def test_remove_client_zeroes_balance_cancels_coupon_and_erases_personal_data(self):
        self.paid("9001", 10000)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        self.paid("9002", 10000)                                            # mais R$ 10 (pendente/liberado)
        self.assertEqual(self.post("tenant-participant-remove", {"confirm": False},
                                   participant_id=self.ana.pk).status_code, 400)
        with DELETE:
            out = self.post("tenant-participant-remove", {"confirm": True, "reason": "pedido da cliente"},
                            participant_id=self.ana.pk)
        self.assertEqual(out.status_code, 200, out.data)
        coupon.refresh_from_db()
        self.assertEqual(coupon.state, "cancelled")
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.status, "withdrawn")
        self.assertEqual(self.ana.display_name, "Cliente removido")
        self.assertNotIn("ana", self.ana.contact_email)
        self.assertEqual(self.balances(), {"pending": 0, "available": 0, "reserved": 0})
        submission = EnrollmentSubmission.objects.get(participant=self.ana)
        self.assertEqual((submission.status, submission.name), ("withdrawn", "Cliente removido"))
        self.assertEqual(self.paid("9003", 10000), "nothing")              # não é mais reconhecida
        self.assertEqual(self.api.get(reverse("tenant-participant-detail", kwargs={
            "tenant_id": self.tenant.id, "participant_id": self.ana.pk})).status_code, 404)

    # ---------- Remover venda de balcão ----------

    def counter_sale(self, cents=12000, state=SaleRecord.State.AWAITING_REVIEW):
        return SaleRecord.objects.create(tenant=self.tenant, participant=self.ana, channel=SaleRecord.Channel.COUNTER,
                                         external_reference="CUPOM-1", eligible_amount_cents=cents,
                                         reported_paid_at=timezone.now(), state=state, submitted_by=self.owner)

    def test_remove_pending_counter_sale_returns_reserved_credit_and_hides_it(self):
        CounterPilot.objects.filter(tenant=self.tenant).update(counter_enabled=True)
        self.paid("9001", 10000)
        release_due(PointLot.objects.get(source_reference="site:9001").wallet)
        sale = self.counter_sale()
        reserve_credit(sale=sale, participant=self.ana, operator=self.owner)
        self.assertEqual(self.balances()["reserved"], 1000)
        self.assertEqual(self.post("manual-sale-remove", {"reason": ""}, sale_id=sale.pk).status_code, 400)
        out = self.post("manual-sale-remove", {"reason": "lançada em dobro"}, sale_id=sale.pk)
        self.assertEqual(out.status_code, 200, out.data)
        self.assertEqual(out.data["returned"], 1000)
        self.assertEqual(self.balances(), {"pending": 0, "available": 1000, "reserved": 0})
        sale.refresh_from_db()
        self.assertIsNotNone(sale.removed_at)
        listing = self.api.get(reverse("manual-sales", kwargs={"tenant_id": self.tenant.id})).data
        self.assertEqual(listing["items"], [])

    def test_remove_confirmed_sale_reverses_its_gain_and_returns_credit_used(self):
        from apps.points.services import create_pending_lot
        CounterPilot.objects.filter(tenant=self.tenant).update(counter_enabled=True)
        self.paid("9001", 10000)
        release_due(PointLot.objects.get(source_reference="site:9001").wallet)
        sale = self.counter_sale()
        reserve_credit(sale=sale, participant=self.ana, operator=self.owner)
        from .pilot import settle_redemption
        settle_redemption(sale, approve=True)                               # crédito usado na venda
        now = timezone.now()
        create_pending_lot(participant=self.ana, channel="counter", source_reference=f"counter:{sale.pk}",
                           eligible_amount_cents=11000, points=1100, rule_version="pilot-vg1",
                           paid_at=now, unlock_at=now + timedelta(days=7),
                           expires_at=now + timedelta(days=37), verification_digest="b" * 64)
        SaleRecord.objects.filter(pk=sale.pk).update(state=SaleRecord.State.VERIFIED_MANUAL)
        out = self.post("manual-sale-remove", {"reason": "teste de caixa"}, sale_id=sale.pk)
        self.assertEqual((out.data["returned"], out.data["reversed"]), (1000, 1100))
        release_due(PointLot.objects.get(source_reference="site:9001").wallet)
        self.assertEqual(self.balances(), {"pending": 0, "available": 1000, "reserved": 0})
        self.assertEqual(CounterRedemption.objects.get(sale=sale).state, "redeemed")   # histórico mantido

    # ---------- Reconhecimento pelo cliente da Nuvemshop ----------

    def test_customer_id_is_remembered_and_recognizes_other_email(self):
        order = {"contact_email": "ana@example.invalid", "customer": {"id": 77, "email": "ana@example.invalid"}}
        self.assertIn("granted", handle_order(tenant=self.tenant, order=order, order_id="9901",
                                              status=SaleRecord.OrderStatus.PAID, total_cents=10000))
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.external_customer_id, "77")
        other = {"contact_email": "ana.trabalho@example.invalid", "customer": {"id": 77, "email": "ana.trabalho@example.invalid"}}
        self.assertIn("granted", handle_order(tenant=self.tenant, order=other, order_id="9902",
                                              status=SaleRecord.OrderStatus.PAID, total_cents=10000))

    # ---------- Crédito retroativo desde a adesão ----------

    def test_credit_since_join_grants_orders_paid_after_joining_only(self):
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        joined = max(self.ana.consent_at, self.ana.joined_at)
        orders = {
            "9950": {"id": 9950, "status": "open", "payment_status": "paid", "currency": "BRL", "total": "100.00",
                     "paid_at": (joined + timedelta(minutes=5)).isoformat(), "contact_email": "ana@example.invalid"},
            "9951": {"id": 9951, "status": "open", "payment_status": "paid", "currency": "BRL", "total": "100.00",
                     "paid_at": (joined - timedelta(days=1)).isoformat(), "contact_email": "ana@example.invalid"},
            "9952": {"id": 9952, "status": "open", "payment_status": "paid", "currency": "BRL", "total": "100.00",
                     "paid_at": (joined + timedelta(minutes=5)).isoformat(), "contact_email": "outra@example.invalid"},
        }
        for oid in orders:
            OrderWebhookEvent.objects.create(tenant=self.tenant, store_id="555", order_id=oid, topic="order/paid",
                                             dedupe_key=("r" + oid).ljust(64, "0"))
        with mock.patch("apps.sales.online._remote", return_value=("555", "t" * 20, "Vidalys QA agent")), \
                mock.patch("apps.nuvemshop.order_readonly.read_order",
                           side_effect=lambda **kw: orders[kw["order_id"]]):
            out = credit_since_join(self.ana)
            again = credit_since_join(self.ana)
        self.assertEqual(out, {"granted": 1, "not_eligible": 1, "other_buyer": 1})
        self.assertEqual(again.get("already"), 1)                           # não duplica
        self.assertTrue(PointLot.objects.filter(source_reference="site:9950").exists())
        self.assertFalse(PointLot.objects.filter(source_reference="site:9951").exists())

    # ---------- Ativação sem pendência ----------

    def test_club_store_activates_on_email_without_flag(self):
        from apps.participants.standalone_activation import club_activates_on_email
        with override_settings(FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED=False):
            self.assertTrue(club_activates_on_email(self.tenant.pk))
            other = Tenant.objects.create(name="Sem clube", slug="sem-clube", status=Tenant.Status.ACTIVE)
            self.assertFalse(club_activates_on_email(other.pk))
