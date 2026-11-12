"""Testes da prévia de pedidos, com cliente OAuth 100% simulado."""
import json
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.tenants.models import Tenant, TenantMembership
from apps.participants.models import ProgramParticipant
from apps.wallets.models import CashbackEvent
from .models import NuvemshopInstallation
from .order_readonly import OrderReadError, summarize_order, read_order

def order(**kwargs):
    value = {
        "id": 87412, "status": "open", "payment_status": "paid",
        "paid_at": "2026-11-11T10:00:00+00:00", "cancelled_at": None,
        "total": "120.90", "currency": "BRL", "gateway": "mercadopago",
        "customer": {"id": 923, "email": "secret@example.invalid"},
    }
    value.update(kwargs)
    return value

class Transport:
    def __init__(self, data):
        self.data = json.dumps(data).encode()
    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.data[:size]

class OrderNormalizationTests(SimpleTestCase):
    def test_remote_call_is_get_and_server_scoped(self):
        transport = Transport(order())
        read_order(store_id=54321, order_id=87412,
                   access_token="synthetic-token-123456", user_agent="Fideliza Test (x@example.invalid)",
                   opener=transport)
        self.assertIn("/2025-03/54321/orders/87412?", transport.request.full_url)
        self.assertEqual(transport.request.get_method(), "GET")
        self.assertEqual(transport.timeout, 8)

    def test_customer_reported_paid_amount_is_a_cross_check_not_psp_proof(self):
        # Até valores iguais na API da plataforma exigem reconciliação no gateway.
        equal = summarize_order(
            order(total_paid_by_customer="120.90"),
            order_id=87412, participant_verified=True,
        )
        self.assertEqual(equal["reported_customer_paid_cents"], 12090)
        self.assertFalse(equal["reported_payment_differs_from_total"])
        self.assertEqual(equal["review_status"], "reported_paid_requires_reconciliation")
        self.assertTrue(equal["reported_paid_amount_is_not_psp_proof"])
        self.assertFalse(equal["credit_eligible"])
        self.assertFalse(equal["cashback_created"])
        # Pagamento parcial, edição de pedido ou taxas geram revisão, não saldo.
        mismatch = summarize_order(
            order(total_paid_by_customer="110.90"),
            order_id=87412, participant_verified=True,
        )
        self.assertEqual(mismatch["reported_customer_paid_cents"], 11090)
        self.assertTrue(mismatch["reported_payment_differs_from_total"])
        self.assertEqual(mismatch["review_status"], "reported_paid_amount_review")
        self.assertFalse(mismatch["credit_eligible"])
        # A prioridade de um estorno/cancelamento não pode ser escondida
        # por uma simples divergência de valor.
        refunded = summarize_order(
            order(payment_status="refunded", total_paid_by_customer="100.00"),
            order_id=87412, participant_verified=True,
        )
        self.assertEqual(refunded["review_status"], "blocked_refund")
        not_provided = summarize_order(
            order(), order_id=87412, participant_verified=True,
        )
        self.assertIsNone(not_provided["reported_customer_paid_cents"])
        self.assertIsNone(not_provided["reported_payment_differs_from_total"])
        for bad in ("NaN", "-1", "1.123", "invalido", True):
            with self.subTest(bad=bad), self.assertRaises(OrderReadError):
                summarize_order(
                    order(total_paid_by_customer=bad),
                    order_id=87412, participant_verified=True,
                )

    def test_payment_status_never_creates_eligible_cashback(self):
        cases = [
            ({}, "reported_paid_requires_reconciliation"),
            ({"gateway": "internal"}, "manual_payment_review"),
            ({"payment_status": "pending"}, "not_paid"),
            ({"payment_status": "refunded"}, "blocked_refund"),
            ({"payment_status": "partially_refunded"}, "blocked_refund"),
            ({"status": "cancelled"}, "blocked_cancelled"),
            ({"paid_at": None}, "payment_date_missing"),
        ]
        for difference, expected in cases:
            with self.subTest(expected=expected):
                value = summarize_order(order(**difference), order_id=87412,
                                        participant_verified=True)
                self.assertEqual(value["review_status"], expected)
                self.assertFalse(value["credit_eligible"])
                self.assertFalse(value["cashback_created"])
                self.assertNotIn("secret@example.invalid", json.dumps(value))
        for invalid in (order(id=17), order(total="-1"), order(total="NaN"),
                        order(total="2.001"), order(currency=""), order(payment_status="other")):
            with self.assertRaises(OrderReadError):
                summarize_order(invalid, order_id=87412, participant_verified=True)

@override_settings(FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True,
                   FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True,
                   FIDELIZA_LEDGER_WRITES_ENABLED=False)
class OrderPreviewApiTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.owner = User.objects.create_user(username="read-order-owner")
        self.analyst = User.objects.create_user(username="read-order-analyst")
        self.foreign = User.objects.create_user(username="read-order-foreign")
        self.tenant = Tenant.objects.create(
            name="Loja piloto", slug="order-test",
            status=Tenant.Status.ACTIVE, platform="nuvemshop", external_store_id="54321")
        self.other = Tenant.objects.create(
            name="Outra loja", slug="order-other",
            status=Tenant.Status.ACTIVE, platform="nuvemshop", external_store_id="98765")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner")
        TenantMembership.objects.create(tenant=self.tenant, user=self.analyst, role="analyst")
        TenantMembership.objects.create(tenant=self.other, user=self.foreign, role="owner")
        self.installed = NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="12345", store_id="54321",
            scope="read_orders,read_customers", token_ciphertext="cipher-test")
        ProgramParticipant.objects.create(
            tenant=self.tenant, external_customer_id="923",
            display_name="Pessoa fictícia", contact_email="secret@example.invalid",
            consent_at=timezone.now(),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE)
        self.cfg = SimpleNamespace(client_id="12345", token_keys="not-real",
                                   user_agent="Fideliza Test (x@example.invalid)")
        self.client.force_login(self.owner)
    def url(self, tenant=None):
        return reverse("nuvemshop-order-preview", kwargs={
            "tenant_id": tenant or self.tenant.pk, "order_id": 87412})
    def test_paid_preview_is_read_only_and_does_not_expose_customer(self):
        with patch("apps.nuvemshop.order_preview_views.config", return_value=self.cfg), \
             patch("apps.nuvemshop.order_preview_views.decrypt_token", return_value="synthetic-token-123456"), \
             patch("apps.nuvemshop.order_preview_views.read_order", return_value=order()) as external:
            response = self.client.get(self.url(), secure=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["review_status"], "reported_paid_requires_reconciliation")
        self.assertTrue(response.json()["participant_verified"])
        self.assertEqual(response.json()["writes_performed"], 0)
        self.assertNotIn("secret@example.invalid", response.content.decode())
        self.assertEqual(external.call_args.kwargs["store_id"], 54321)
        self.assertEqual(CashbackEvent.objects.count(), 0)
    def test_scopes_disabled_roles_and_tenant_isolation(self):
        with override_settings(FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=False), \
             patch("apps.nuvemshop.order_preview_views.read_order") as external:
            self.assertEqual(self.client.get(self.url(), secure=True).status_code, 409)
            external.assert_not_called()
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 403)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 404)
        self.client.force_login(self.owner)
        self.installed.scope = "read_products"
        self.installed.save(update_fields=["scope"])
        with patch("apps.nuvemshop.order_preview_views.config", return_value=self.cfg), \
             patch("apps.nuvemshop.order_preview_views.read_order") as external:
            self.assertEqual(self.client.get(self.url(), secure=True).status_code, 409)
            external.assert_not_called()
    def test_missing_customer_scope_blocks_identity_match(self):
        self.installed.scope = "read_orders"
        self.installed.save(update_fields=["scope"])
        with patch("apps.nuvemshop.order_preview_views.config", return_value=self.cfg), \
             patch("apps.nuvemshop.order_preview_views.decrypt_token", return_value="synthetic-token-123456"), \
             patch("apps.nuvemshop.order_preview_views.read_order", return_value=order()):
            result = self.client.get(self.url(), secure=True)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["review_status"], "customer_not_verified")
