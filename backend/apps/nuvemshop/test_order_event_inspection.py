"""Testes da inspeção de evento; nenhuma carteira recebe crédito."""
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEvent
from .models import NuvemshopInstallation
from .order_webhook_models import OrderWebhookEvent


@override_settings(
    FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True,
    FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class OrderEventInspectionTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.owner = User.objects.create_user(username="event-inspect-owner")
        self.analyst = User.objects.create_user(username="event-inspect-analyst")
        self.foreign_user = User.objects.create_user(username="event-inspect-foreign")
        self.tenant = Tenant.objects.create(
            name="Loja piloto", slug="event-inspect",
            platform="nuvemshop", external_store_id="54321",
            status=Tenant.Status.ACTIVE,
        )
        self.foreign = Tenant.objects.create(
            name="Loja estrangeira", slug="event-inspect-foreign",
            platform="nuvemshop", external_store_id="98765",
            status=Tenant.Status.ACTIVE,
        )
        for user, tenant, role in (
            (self.owner, self.tenant, "owner"),
            (self.analyst, self.tenant, "analyst"),
            (self.foreign_user, self.foreign, "owner"),
        ):
            TenantMembership.objects.create(user=user, tenant=tenant, role=role)
        self.installation = NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="12345", store_id="54321",
            scope="read_orders,read_customers", token_ciphertext="cipher-text",
        )
        ProgramParticipant.objects.create(
            tenant=self.tenant, external_customer_id="923",
            consent_at=timezone.now(), consent_channel="customer_portal",
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )
        self.event = OrderWebhookEvent.objects.create(
            tenant=self.tenant, store_id="54321", order_id="87412",
            topic="order/paid", event_launch_ts=1794420000,
            dedupe_key="d"*64,
        )
        self.url = reverse("nuvemshop-order-event-inspect", kwargs={
            "tenant_id": self.tenant.id, "event_id": self.event.id,
        })
        self.client.force_login(self.owner)
        self.order = {
            "id": 87412, "status": "open", "payment_status": "paid",
            "paid_at": "2026-11-11T10:00:00+00:00",
            "cancelled_at": None, "total": "120.90", "currency": "BRL",
            "gateway": "mercadopago", "customer": {
                "id": 923, "email": "secret@example.invalid",
            },
        }

    def test_event_recheck_reads_official_order_without_cashback(self):
        cfg = SimpleNamespace(client_id="12345", token_keys="synthetic-keys",
                              user_agent="Fideliza Test (x@example.invalid)")
        with patch("apps.nuvemshop.order_preview_views.config", return_value=cfg), \
             patch("apps.nuvemshop.order_preview_views.decrypt_token", return_value="test-valid-token-123456"), \
             patch("apps.nuvemshop.order_preview_views.read_order", return_value=self.order) as external:
            result = self.client.get(self.url, secure=True)
        self.assertEqual(result.status_code, 200, result.content)
        body = result.json()
        self.assertEqual(body["order_id"], "87412")
        self.assertEqual(body["review_status"], "reported_paid_requires_reconciliation")
        self.assertEqual(body["event_receipt"]["topic"], "order/paid")
        self.assertFalse(body["event_proves_payment"])
        self.assertFalse(body["credit_eligible"])
        self.assertFalse(body["cashback_created"])
        self.assertEqual(body["writes_performed"], 0)
        self.assertNotIn("secret@example.invalid", result.content.decode())
        self.assertEqual(external.call_args.kwargs["order_id"], 87412)
        self.assertEqual(CashbackEvent.objects.count(), 0)
        self.assertEqual(OrderWebhookEvent.objects.count(), 1)

    def test_cancellation_and_manual_payment_not_eligible(self):
        cfg = SimpleNamespace(client_id="12345", token_keys="synthetic-keys",
                              user_agent="Fideliza Test (x@example.invalid)")
        for change, expected in (
            ({"gateway": "internal"}, "manual_payment_review"),
            ({"payment_status": "refunded"}, "blocked_refund"),
            ({"status": "cancelled"}, "blocked_cancelled"),
        ):
            cache.clear()
            with self.subTest(expected=expected), \
                 patch("apps.nuvemshop.order_preview_views.config", return_value=cfg), \
                 patch("apps.nuvemshop.order_preview_views.decrypt_token", return_value="test-valid-token-123456"), \
                 patch("apps.nuvemshop.order_preview_views.read_order", return_value={**self.order, **change}):
                result = self.client.get(self.url, secure=True)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["review_status"], expected)
                self.assertFalse(result.json()["credit_eligible"])

    def test_roles_tenant_and_flags(self):
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 403)
        self.client.force_login(self.foreign_user)
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 404)
        self.client.force_login(self.owner)
        with override_settings(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=False):
            self.assertEqual(self.client.get(self.url, secure=True).status_code, 409)
        with override_settings(FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=False):
            self.assertEqual(self.client.get(self.url, secure=True).status_code, 409)
        self.installation.scope = "read_customers"
        self.installation.save(update_fields=["scope"])
        with patch("apps.nuvemshop.order_preview_views.config") as cfg, \
             patch("apps.nuvemshop.order_preview_views.read_order") as external:
            cfg.return_value = SimpleNamespace(client_id="12345", token_keys="test",
                                               user_agent="Fideliza Test")
            self.assertEqual(self.client.get(self.url, secure=True).status_code, 409)
            external.assert_not_called()
