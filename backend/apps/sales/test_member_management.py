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
        from apps.participants.models import ParticipantRemoval
        record = ParticipantRemoval.objects.get(participant=self.ana)
        self.assertEqual((record.reason, record.coupons_cancelled, record.data_result), ("pedido da cliente", 1, "erased"))
        self.assertGreater(record.reversed_units, 0)                       # saldo zerado ficou registrado

    def test_remove_client_frees_the_nuvemshop_customer_link(self):
        from apps.participants.enrollment_models import EnrollmentCustomerLink
        submission = EnrollmentSubmission.objects.get(participant=self.ana)
        EnrollmentCustomerLink.objects.create(tenant=self.tenant, submission=submission, participant=self.ana,
                                              external_customer_id="4242")
        ProgramParticipant.objects.filter(pk=self.ana.pk).update(external_customer_id="4242")
        self.assertEqual(self.post("tenant-participant-remove", {"confirm": True},
                                   participant_id=self.ana.pk).status_code, 200)
        self.assertFalse(EnrollmentCustomerLink.objects.filter(external_customer_id="4242").exists())
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.external_customer_id)

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

    def confirmed_counter_sale_with_credit(self, units=1000):
        from apps.points.services import create_pending_lot
        CounterPilot.objects.filter(tenant=self.tenant).update(counter_enabled=True)
        sale = self.counter_sale(state=SaleRecord.State.VERIFIED_MANUAL)
        now = timezone.now()
        lot, _ = create_pending_lot(participant=self.ana, channel="counter", source_reference=f"counter:{sale.pk}",
                                    eligible_amount_cents=10000, points=units, rule_version="pilot-vg1",
                                    paid_at=now, unlock_at=now, expires_at=now + timedelta(days=30),
                                    verification_digest="e" * 64)
        release_due(lot.wallet)
        return sale, lot

    def spend(self, lot, amount, key):
        from apps.points.models import PointEvent
        from apps.points.services import transition_points
        transition_points(lot_id=lot.pk, kind=PointEvent.Kind.RESERVE, amount=amount, idempotency_key=key + "-r")
        transition_points(lot_id=lot.pk, kind=PointEvent.Kind.REDEEM, amount=amount, idempotency_key=key,
                          external_receipt="teste:" + key)

    def test_annul_sale_whose_credit_was_spent_recovers_from_other_balance(self):
        sale, lot = self.confirmed_counter_sale_with_credit()
        self.spend(lot, 1000, "gasto-1")                                   # cliente usou os R$ 10
        self.paid("9001", 20000)                                           # depois ganhou R$ 20 no site
        release_due(lot.wallet)
        out = self.post("manual-sale-remove", {"reason": "venda lançada errada"}, sale_id=sale.pk)
        self.assertEqual(out.status_code, 200, out.data)
        self.assertEqual(out.data["recovered"], 1000)
        self.assertEqual(self.balances()["available"], 1000)               # 2000 - 1000 recuperado

    def test_annul_sale_whose_credit_was_spent_without_balance_is_blocked(self):
        sale, lot = self.confirmed_counter_sale_with_credit()
        self.spend(lot, 1000, "gasto-2")
        out = self.post("manual-sale-remove", {"reason": "venda lançada errada"}, sale_id=sale.pk)
        self.assertEqual(out.status_code, 409)
        self.assertIn("já usou", out.data["detail"])
        sale.refresh_from_db()
        self.assertIsNone(sale.removed_at)                                  # nada mudou

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

    # ---------- Crédito retroativo desde a adesão (mesma reconsulta dos pedidos normais) ----------

    def test_credit_since_join_reuses_the_recheck_path_for_her_orders_only(self):
        from apps.nuvemshop.models import NuvemshopOrderRecheck
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        events = {oid: OrderWebhookEvent.objects.create(tenant=self.tenant, store_id="555", order_id=oid,
                                                         topic="order/paid", dedupe_key=("r" + oid).ljust(64, "0"))
                  for oid in ("9950", "9951", "9952")}
        self.paid("9951", 10000)                                           # já tem saldo: não relê
        calls = []

        def fake_recheck(*, event_id, reprocess=False, **kw):
            calls.append((event_id, reprocess))
            if event_id == events["9952"].pk:
                raise RuntimeError("Nuvemshop fora do ar")
            return self.paid("9950", 10000)                                # o caminho normal concede

        with mock.patch("apps.sales.online._orders_for_member", return_value=["9950", "9951", "9952"]), \
                mock.patch("apps.nuvemshop.order_recheck_service.recheck_order_event", side_effect=fake_recheck):
            out = credit_since_join(self.ana)
        self.assertEqual({c[0] for c in calls}, {events["9950"].pk, events["9952"].pk})
        self.assertTrue(all(reprocess for _, reprocess in calls))           # sempre pela reconsulta
        self.assertEqual((out["granted"], out["retry"]), (1, 1))
        self.assertEqual(NuvemshopOrderRecheck.objects.get(event=events["9952"]).status, "club_retry")

    def test_order_found_without_webhook_gets_a_backfill_entry_through_the_same_recheck(self):
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        self.tenant.external_store_id = "555"
        self.tenant.save(update_fields=["external_store_id"])
        calls = []

        def fake_recheck(*, event_id, reprocess=False, **kw):
            calls.append((OrderWebhookEvent.objects.get(pk=event_id), reprocess))
            return None

        with mock.patch("apps.sales.online._orders_for_member", return_value=["9980"]), \
                mock.patch("apps.nuvemshop.order_recheck_service.recheck_order_event", side_effect=fake_recheck):
            out = credit_since_join(self.ana)
            again = credit_since_join(self.ana)
        event, reprocess = calls[0]
        self.assertEqual((event.order_id, event.topic, event.store_id, reprocess), ("9980", "reconcile/backfill", "555", True))
        self.assertEqual((out["backfill"], again.get("backfill", 0)), (1, 0))   # entrada criada uma vez só
        self.assertEqual(OrderWebhookEvent.objects.filter(order_id="9980").count(), 1)

    def test_search_unavailable_retries_the_task_with_the_same_cursor(self):
        from apps.sales.tasks import credit_since_join_task
        with mock.patch("apps.sales.online.credit_since_join", return_value={"retry_later": 1}), \
                mock.patch.object(credit_since_join_task, "retry", side_effect=RuntimeError("retry")) as retry:
            with self.assertRaises(RuntimeError):
                credit_since_join_task.run(str(self.ana.pk), "123")
        retry.assert_called_once()

    def test_retro_cursor_moves_past_ineligible_orders_in_batches(self):
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        ids = [str(10000 + i) for i in range(120)]                         # mais de 50 pedidos, nenhum elegível
        for oid in ids:
            OrderWebhookEvent.objects.create(tenant=self.tenant, store_id="555", order_id=oid,
                                             topic="order/paid", dedupe_key=("c" + oid).ljust(64, "0"))
        seen = []

        def fake_recheck(*, event_id, reprocess=False, **kw):
            seen.append(OrderWebhookEvent.objects.get(pk=event_id).order_id)
            return None                                                     # inelegível: não concede

        with mock.patch("apps.sales.online._orders_for_member", return_value=list(reversed(ids))), \
                mock.patch("apps.nuvemshop.order_recheck_service.recheck_order_event", side_effect=fake_recheck):
            first = credit_since_join(self.ana, batch=50)
            second = credit_since_join(self.ana, batch=50, after=first["cursor"])
            third = credit_since_join(self.ana, batch=50, after=second["cursor"])
        self.assertEqual(seen, ids)                                         # cada pedido uma vez, em ordem
        self.assertEqual((first["nothing"], second["nothing"], third["nothing"]), (50, 50, 20))
        self.assertNotIn("cursor", third)                                   # acabou

    def test_member_search_reads_every_page_by_update_date(self):
        from apps.sales import online
        pages = {1: [{"id": i} for i in range(1, 201)], 2: [{"id": i} for i in range(201, 231)]}
        urls = []

        class Resp:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return self.body

        class Opener:
            def open(self, request, timeout):
                import json
                from urllib.parse import parse_qs, urlparse
                urls.append(request.full_url)
                page = int(parse_qs(urlparse(request.full_url).query)["page"][0])
                return Resp(json.dumps(pages.get(page, [])).encode())

        with mock.patch("apps.sales.online._remote", return_value=("555", "tok", "ua")):
            found = online._orders_for_member(self.ana, timezone.now() - timedelta(days=1), opener=Opener())
        self.assertEqual(len(found), 230)
        self.assertEqual(len(urls), 2)                                      # parou na página incompleta
        self.assertIn("updated_at_min", urls[0])                            # criado antes, pago depois: aparece
        self.assertNotIn("created_at_min", urls[0])

    def test_recheck_without_paid_date_goes_to_review_never_grants(self):
        from apps.nuvemshop.order_recheck_service import RecheckBlocked, _run_club
        from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
        event = OrderWebhookEvent.objects.create(tenant=self.tenant, store_id="555", order_id="9970",
                                                 topic="order/paid", dedupe_key="z".ljust(64, "0"))
        order = {"id": 9970, "status": "open", "payment_status": "paid", "currency": "BRL", "total": "120.00",
                 "gateway": "pagarme", "contact_email": "ana@example.invalid", "contact_phone": "", "coupon": []}
        with self.assertRaises(RecheckBlocked):
            _run_club(event=event, tenant=self.tenant, order=order, grant=True)
        self.assertFalse(PointLot.objects.filter(source_reference="site:9970").exists())

    def test_order_paid_before_joining_never_grants(self):
        before = (self.ana.joined_at - timedelta(days=1)).isoformat()
        order = {"contact_email": "ana@example.invalid", "paid_at": before}
        out = handle_order(tenant=self.tenant, order=order, order_id="9960",
                           status=SaleRecord.OrderStatus.PAID, total_cents=10000)
        self.assertIn("before_join", out)
        self.assertFalse(PointLot.objects.filter(source_reference="site:9960").exists())

    # ---------- Ativação sem pendência ----------

    def test_club_store_activates_on_email_without_flag(self):
        from apps.participants.standalone_activation import club_activates_on_email
        with override_settings(FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED=False):
            self.assertTrue(club_activates_on_email(self.tenant.pk))
            other = Tenant.objects.create(name="Sem clube", slug="sem-clube", status=Tenant.Status.ACTIVE)
            self.assertFalse(club_activates_on_email(other.pk))
