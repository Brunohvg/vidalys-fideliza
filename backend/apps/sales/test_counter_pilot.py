"""Piloto de pontos no balcão: portas de segurança, tetos, vale reservado e desfazer."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.models import ProgramParticipant
from apps.points.models import PointLot
from apps.points.services import create_pending_lot
from apps.tenants.models import Tenant, TenantMembership
from .models import CounterPilot, CounterRedemption, DiscountRewardDraft, PointRuleDraft, SaleRecord
from .pilot import counter_wallet, pilot_enabled, wallet_balances


class CounterPilotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="pilot-owner")
        self.admin = User.objects.create_user(username="pilot-admin")
        self.tenant = Tenant.objects.create(name="Bibelô QA", slug="pilot-qa", platform="independent",
                                            status=Tenant.Status.ACTIVE)
        self.other = Tenant.objects.create(name="Outra", slug="pilot-other", platform="independent",
                                           status=Tenant.Status.ACTIVE)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(user=self.admin, tenant=self.tenant, role=TenantMembership.Role.ADMIN)
        TenantMembership.objects.create(user=self.owner, tenant=self.other, role=TenantMembership.Role.OWNER)
        self.ana = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Ana", contact_email="ana@example.invalid",
            external_customer_id=None, consent_at=timezone.now() - timedelta(days=30),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL, terms_version="v1",
            status=ProgramParticipant.Status.ACTIVE,
        )
        # 3 pontos a cada R$ 1,00 = 3%; carência zero para testar a liberação.
        PointRuleDraft.objects.create(tenant=self.tenant, points=3, per_cents=100, hold_days=0,
                                      validity_days=90, updated_by=self.owner)
        self.reward = DiscountRewardDraft.objects.create(
            tenant=self.tenant, title="Vale R$ 10", points_cost=1000, discount_cents=1000,
            min_order_cents=5000, publication_status=DiscountRewardDraft.PublicationStatus.PUBLISHED,
            allowed_channels="counter", updated_by=self.owner,
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.seq = 0

    def post(self, name, payload, **kwargs):
        self.client.get(reverse("auth-session"))
        return self.client.post(reverse(name, kwargs={"tenant_id": self.tenant.id, **kwargs}), payload,
                                format="json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

    def sale(self, cents, **extra):
        self.seq += 1
        body = {"reference": f"VENDA-{self.seq:05d}", "eligible_amount_cents": cents,
                "participant_id": str(self.ana.id), "reported_paid_at": timezone.now().isoformat(),
                "evidence_reference": f"CUPOM-{self.seq:05d}", **extra}
        return self.post("manual-sales", body)

    def approve(self, sale_id):
        return self.post("manual-sale-review", {"decision": "approve", "note": "Conferida com o cupom."},
                         sale_id=sale_id)

    def activate(self):
        return self.post("counter-pilot", {"active": True})

    def test_off_by_default_and_never_outside_homolog_or_allowlist(self):
        self.assertFalse(pilot_enabled(self.tenant))
        with override_settings(FIDELIZA_ENVIRONMENT="production", FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)})):
            self.assertEqual(self.activate().status_code, 409)
        with override_settings(FIDELIZA_ENVIRONMENT="homolog", FIDELIZA_PILOT_TENANTS=frozenset()):
            self.assertEqual(self.activate().status_code, 409)
        sale = self.sale(10000).data["sale"]
        self.assertEqual(self.approve(sale["id"]).data["points"], 0)
        self.assertFalse(PointLot.objects.exists())

    def test_only_owner_toggles(self):
        with override_settings(FIDELIZA_ENVIRONMENT="homolog", FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)})):
            self.client.force_login(self.admin)
            self.assertEqual(self.activate().status_code, 403)

    def test_confirm_grants_capped_points_and_pause_stops(self):
        with override_settings(FIDELIZA_ENVIRONMENT="homolog", FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)})):
            state = self.activate().data
            self.assertTrue(state["active"])
            self.post("counter-pilot", {"per_sale_cap_points": 500, "budget_points": 800})
            first = self.sale(10000).data["sale"]          # 300 pts
            self.assertEqual(first["points_preview"], 300)
            self.assertEqual(self.approve(first["id"]).data["points"], 300)
            big = self.sale(50000).data["sale"]            # 1500 pts -> teto 500
            self.assertTrue(big["points_capped"])
            self.assertEqual(self.approve(big["id"]).data["points"], 500)
            last = self.sale(10000).data["sale"]           # orçamento: só restam 0
            self.assertEqual(self.approve(last["id"]).data["points_reason"], "budget")
            self.assertEqual(sum(PointLot.objects.values_list("points_issued", flat=True)), 800)
            # Liberação acontece ao consultar (carência zero).
            self.assertEqual(counter_wallet(self.ana)["available"], 800)
            self.post("counter-pilot", {"active": False})
            self.assertFalse(pilot_enabled(self.tenant))
            paused = self.sale(10000).data["sale"]
            self.assertEqual(self.approve(paused["id"]).data["points"], 0)

    def test_reward_reserved_then_redeemed_or_returned(self):
        with override_settings(FIDELIZA_ENVIRONMENT="homolog", FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)}),
                               FIDELIZA_POINTS_WRITES_ENABLED=False):
            self.activate()
            for _ in range(4):                                    # 4 x 300 = 1200 pts
                self.approve(self.sale(10000).data["sale"]["id"])
            self.assertEqual(counter_wallet(self.ana)["available"], 1200)
            self.assertEqual(self.sale(4000, reward_id=str(self.reward.id)).status_code, 409)  # abaixo do mínimo
            used = self.sale(15000, reward_id=str(self.reward.id))
            self.assertEqual(used.status_code, 201, used.data)
            self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1000)
            # Pontos da venda com vale: 3% de R$ 140 (paga) = 420.
            self.assertEqual(self.approve(used.data["sale"]["id"]).data["points"], 420)
            redemption = CounterRedemption.objects.get()
            self.assertEqual(redemption.state, "redeemed")
            counter_wallet(self.ana)
            self.assertEqual(wallet_balances(self.ana)[1], {"pending": 0, "available": 620, "reserved": 0})
            # Desfazer devolve a reserva.
            for _ in range(2):
                self.approve(self.sale(10000).data["sale"]["id"])
            again = self.sale(6000, reward_id=str(self.reward.id)).data["sale"]
            self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1000)
            self.assertEqual(self.post("manual-sale-undo", {}, sale_id=again["id"]).status_code, 200)
            self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 0)
            self.assertEqual(SaleRecord.objects.get(pk=again["id"]).state, "rejected")

    def test_batch_skips_alerts_and_undo_rules(self):
        with override_settings(FIDELIZA_ENVIRONMENT="homolog", FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)})):
            self.activate()
            normal = self.sale(10000).data["sale"]["id"]
            huge = self.sale(900000).data["sale"]["id"]           # sem histórico: > R$ 2.000 tem alerta
            noon = timezone.localtime().replace(hour=12, minute=0)
            SaleRecord.objects.filter(pk__in=[normal, huge]).update(created_at=noon)
            listing = self.client.get(reverse("manual-sales", kwargs={"tenant_id": self.tenant.id})).data
            alerts = {i["id"]: i["alerts"] for i in listing["items"]}
            self.assertTrue(alerts[huge])
            result = self.post("manual-sale-confirm-batch", {"ids": [normal, huge]}).data
            self.assertEqual(result["confirmed"], [normal])
            self.assertEqual(result["skipped"], [huge])
            # Venda já conferida não pode ser desfeita; outro usuário também não.
            self.assertEqual(self.post("manual-sale-undo", {}, sale_id=normal).status_code, 409)
            self.client.force_login(self.admin)
            self.assertEqual(self.post("manual-sale-undo", {}, sale_id=huge).status_code, 409)
            self.client.force_login(self.owner)
            SaleRecord.objects.filter(pk=huge).update(created_at=timezone.now())
            self.assertEqual(self.post("manual-sale-undo", {}, sale_id=huge).status_code, 200)
            late = self.sale(10000).data["sale"]["id"]
            SaleRecord.objects.filter(pk=late).update(created_at=timezone.now() - timedelta(minutes=6))
            self.assertEqual(self.post("manual-sale-undo", {}, sale_id=late).status_code, 409)

    def test_other_store_cannot_use_pilot(self):
        with override_settings(FIDELIZA_ENVIRONMENT="homolog", FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)})):
            self.activate()
            self.assertFalse(pilot_enabled(self.other))
            bob = ProgramParticipant.objects.create(
                tenant=self.other, display_name="Bob", contact_email="bob@example.invalid",
                external_customer_id=None, consent_at=timezone.now() - timedelta(days=3),
                consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL, terms_version="v1",
                status=ProgramParticipant.Status.ACTIVE,
            )
            now = timezone.now()
            with self.assertRaises(PermissionError):
                create_pending_lot(participant=bob, channel="counter", source_reference="counter:x-1",
                                   eligible_amount_cents=100, points=3, rule_version="pilot-v1", paid_at=now,
                                   unlock_at=now, expires_at=now + timedelta(days=1), verification_digest="a" * 64)
            wallet = self.client.get(reverse("counter-wallet", kwargs={
                "tenant_id": self.tenant.id, "participant_id": bob.id}))
            self.assertEqual(wallet.status_code, 404)
            self.assertFalse(CounterPilot.objects.filter(tenant=self.other).exists())
