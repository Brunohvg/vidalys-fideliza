"""Política central teste x comercial: tetos por modo, requisitos por canal, liberação só por
superusuário, baixas que continuam com o clube pausado e a flag global que não fura a política."""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.enrollment_models import ProgramTerms
from apps.points.models import PointEvent, PointLot
from apps.points.services import create_pending_lot
from apps.tenants.models import TenantMembership
from .models import CounterPilot, OnlineCoupon, ProgramMode
from .online import issue_coupon
from .pilot import points_for, wallet_balances
from .policy import can_operate, effective_budget, effective_per_sale
from .test_online_redemption import FLAGS, REMOTE, StoreFixture


@override_settings(**FLAGS)
class OperationPolicyTests(StoreFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.root = get_user_model().objects.create_superuser(username="vidalys-root", password="x" * 20)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        self.api = APIClient()
        self.api.force_login(self.owner)

    def pilot(self):
        return CounterPilot.objects.get(tenant=self.tenant)

    def operate(self, mode, actor="vidalys-root"):
        if mode == "commercial":                                # comercial exige carência de 7 dias no site
            ProgramMode.objects.filter(tenant=self.tenant).update(giftback_hold_days=7)
        call_command("set_store_operation", "--tenant", self.tenant.slug, "--mode", mode,
                     "--actor", actor, "--confirm", mode.upper(), stdout=StringIO())

    def caps(self, **data):
        return self.api.post(reverse("counter-pilot", kwargs={"tenant_id": self.tenant.id}), data, format="json")

    def test_every_store_starts_in_test_mode_with_low_fixed_caps(self):
        self.assertEqual(self.pilot().operation_mode, "test")
        CounterPilot.objects.filter(tenant=self.tenant).update(per_sale_cap_points=90_000, budget_points=9_000_000)
        self.assertEqual(effective_per_sale(self.pilot()), 5_000)              # R$ 50 por compra
        self.assertEqual(effective_budget(self.pilot()), 200_000)              # R$ 2.000 no total
        # Giftback 10% de R$ 1.000 = R$ 100, mas no teste uma compra gera no máximo R$ 50 (e o teto do giftback, R$ 20).
        self.assertEqual(points_for(self.tenant.pk, 100_000)[0], 2_000)

    def test_panel_rejects_caps_above_mode_limit_in_reais(self):
        bad = self.caps(per_sale_cap_points=5_001)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("No modo teste, o teto por venda vai até R$ 50,00", bad.data["detail"])
        self.assertEqual(self.caps(budget_points=200_001).status_code, 400)
        ok = self.caps(per_sale_cap_points=5_000, budget_points=200_000)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["operation"]["mode"], "test")
        self.assertEqual(ok.data["operation"]["max_budget"], 200_000)

    def test_commercial_only_by_superuser_with_confirmation_and_requirements(self):
        with self.assertRaises(CommandError):
            self.operate("commercial", actor="online-owner")                    # dono da loja não libera
        with self.assertRaises(CommandError):
            call_command("set_store_operation", "--tenant", self.tenant.slug, "--mode", "commercial",
                         "--actor", "vidalys-root", "--confirm", "SIM", stdout=StringIO())
        ProgramTerms.objects.filter(tenant=self.tenant).update(active=False)
        with self.assertRaisesMessage(CommandError, "Regulamento e aviso de privacidade publicados"):
            self.operate("commercial")
        self.assertEqual(self.pilot().operation_mode, "test")                  # nada mudou
        ProgramTerms.objects.filter(tenant=self.tenant).update(active=True)
        self.operate("commercial")
        pilot = self.pilot()
        self.assertEqual((pilot.operation_mode, pilot.commercial_by), ("commercial", self.root))
        self.assertEqual(self.caps(per_sale_cap_points=20_000).status_code, 200)   # R$ 200 no comercial
        self.assertEqual(self.caps(per_sale_cap_points=20_001).status_code, 400)
        self.operate("test")                                                   # voltar é sempre aceito
        self.assertEqual(effective_per_sale(self.pilot()), 5_000)

    def test_commercial_blocks_when_requirement_drops_but_test_mode_keeps_testing_free(self):
        self.operate("commercial")
        self.assertTrue(can_operate(self.tenant))
        ProgramTerms.objects.filter(tenant=self.tenant).update(active=False)    # regulamento saiu do ar
        self.assertFalse(can_operate(self.tenant))
        self.assertEqual(self.paid("9301", 10_000), "nothing")                  # não ganha
        with self.assertRaises(PermissionError):
            create_pending_lot(participant=self.ana, channel="counter", source_reference="counter:policy-1",
                               eligible_amount_cents=100, points=3, rule_version="pilot-vg1",
                               paid_at=timezone.now(), unlock_at=timezone.now(),
                               expires_at=timezone.now() + timedelta(days=30), verification_digest="a" * 64)
        self.operate("test")
        self.assertTrue(can_operate(self.tenant))                                # teste continua livre
        self.assertIn("granted", self.paid("9302", 10_000))

    def test_stuck_coupon_blocks_only_site_coupons_in_commercial(self):
        self.operate("commercial")
        self.paid("9001", 10_000)
        OnlineCoupon.objects.create(tenant=self.tenant, participant=self.ana, source="giftback", code="LOJAON-STUCK001",
                                    points=1, discount_cents=1, min_order_cents=2, expires_at=timezone.now() + timedelta(days=5),
                                    state="uncertain")
        OnlineCoupon.objects.filter(code="LOJAON-STUCK001").update(created_at=timezone.now() - timedelta(hours=25))
        self.assertFalse(can_operate(self.tenant, "site_coupon"))
        self.assertTrue(can_operate(self.tenant, "site_earn"))
        self.assertTrue(can_operate(self.tenant))                               # balcão segue
        blockers = self.caps(budget_points=1000).data["operation"]["blockers"]
        self.assertIn("Nenhum cupom sem confirmação há mais de 24 horas", blockers)

    def test_paused_club_still_settles_coupon_used_on_site(self):
        self.paid("9001", 10_000)
        with REMOTE:
            coupon = issue_coupon(self.ana)
        CounterPilot.objects.filter(tenant=self.tenant).update(active=False)    # lojista pausou
        self.assertIn("coupon_used", self.paid("9400", 12_000, codes=[coupon.code]))
        coupon.refresh_from_db()
        self.assertEqual(coupon.state, "used")
        self.assertEqual(PointEvent.objects.filter(kind="redeem").count(), 1)
        self.assertFalse(PointLot.objects.filter(source_reference="site:9400").exists())  # pausado: não ganha
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 0)

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_global_flag_does_not_bypass_store_policy(self):
        CounterPilot.objects.filter(tenant=self.tenant).update(active=False)
        with self.assertRaises(PermissionError):
            create_pending_lot(participant=self.ana, channel="counter", source_reference="counter:policy-2",
                               eligible_amount_cents=100, points=3, rule_version="pilot-vg1",
                               paid_at=timezone.now(), unlock_at=timezone.now(),
                               expires_at=timezone.now() + timedelta(days=30), verification_digest="a" * 64)

    def test_readiness_report_is_read_only_and_shows_store_without_pii(self):
        out = StringIO()
        call_command("club_readiness", "--tenant", self.tenant.slug, "--skip-workers", stdout=out)
        text = out.getvalue()
        self.assertIn("Banco com todas as migrações aplicadas", text)
        self.assertIn("Rotina agendada: sales.online_coupon_refresh", text)
        self.assertIn("Loja loja-online", text)
        self.assertIn("modo teste", text)
        self.assertIn("Tetos em vigor: R$ 50,00 por compra · R$ 500,00 no total", text)
        self.assertIn("Resultado: OK", text)
        self.assertNotIn("ana@example.invalid", text)
        self.assertNotIn("Ana", text)
        ProgramTerms.objects.filter(tenant=self.tenant).update(active=False)
        self.operate("test")
        CounterPilot.objects.filter(tenant=self.tenant).update(operation_mode="commercial", commercial_at=timezone.now())
        with self.assertRaises(SystemExit):                                 # comercial com bloqueio = falha
            call_command("club_readiness", "--tenant", self.tenant.slug, "--skip-workers", stdout=StringIO())

    def test_commercial_site_requires_seven_day_hold(self):
        self.operate("commercial")
        ProgramMode.objects.filter(tenant=self.tenant).update(giftback_hold_days=2)
        self.assertFalse(can_operate(self.tenant, "site_earn"))
        self.assertFalse(can_operate(self.tenant, "site_coupon"))
        self.assertTrue(can_operate(self.tenant))                               # balcão segue

    def test_nuvemshop_store_runs_site_only_until_counter_is_turned_on(self):
        from .pilot import counter_enabled
        from .policy import channels
        self.assertEqual(channels(self.tenant), {"site": True, "counter": False})
        self.assertFalse(counter_enabled(self.tenant))
        self.assertTrue(can_operate(self.tenant, "site_earn"))                  # site segue normal
        on = self.caps(counter_enabled=True)
        self.assertEqual(on.data["channels"], {"site": True, "counter": True})
        self.assertTrue(counter_enabled(self.tenant))
