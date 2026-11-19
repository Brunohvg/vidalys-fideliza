"""Clube no site: ganhar em pedido pago, cupom único reservado, uso no site, no caixa e vencimento.

A Nuvemshop é simulada (_create_remote/_delete_remote); nada sai da máquina de teste.
"""
import hashlib
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.nuvemshop.models import NuvemshopInstallation
from apps.participants.enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms
from apps.participants.models import ProgramParticipant
from apps.points.models import PointLot
from apps.points.services import lot_balances
from apps.tenants.models import Tenant
from .models import CounterPilot, OnlineCoupon, ProgramMode, SaleRecord
from .online import CouponUnavailable, handle_order, issue_coupon, refresh_tenant, site_status
from .pilot import wallet_balances

FLAGS = dict(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True, FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED=True,
             FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True, FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True)
REMOTE = mock.patch("apps.sales.online._create_remote", return_value=("777", "https://loja.example/discount/X"))
DELETE = mock.patch("apps.sales.online._delete_remote", return_value=True)


@override_settings(**FLAGS)
class OnlineRedemptionTests(TestCase):
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

    def test_remote_failure_returns_reservation(self):
        self.paid("9001", 15776)
        with mock.patch("apps.sales.online._create_remote", side_effect=RuntimeError("down")), \
                self.assertRaises(CouponUnavailable):
            issue_coupon(self.ana)
        self.assertEqual(OnlineCoupon.objects.get().state, "failed")
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 0)
