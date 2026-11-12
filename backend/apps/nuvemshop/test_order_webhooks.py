"""Inbox de pedidos: HMAC real, concorrência lógica e zero crédito financeiro."""
import hashlib
import hmac
import json
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEntry, CashbackEvent
from .models import NuvemshopInstallation
from .order_webhook_models import OrderWebhookEvent

SECRET = "synthetic-hmac-secret-for-orders"


@override_settings(
    FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class OrderWebhookTests(TestCase):
    def setUp(self):
        context = patch.dict(os.environ, {
            "NUVEMSHOP_CLIENT_ID": "12345",
            "NUVEMSHOP_CLIENT_SECRET": SECRET,
        })
        context.start()
        self.addCleanup(context.stop)
        self.client = Client(enforce_csrf_checks=True)
        User = get_user_model()
        self.owner = User.objects.create_user(username="webhook-owner")
        self.analyst = User.objects.create_user(username="webhook-analyst")
        self.other_user = User.objects.create_user(username="webhook-foreign")
        self.tenant = Tenant.objects.create(
            name="Webhook piloto", slug="webhook-pilot",
            platform="nuvemshop", external_store_id="54321",
            status=Tenant.Status.ACTIVE,
        )
        self.other = Tenant.objects.create(
            name="Webhook outro", slug="webhook-other",
            platform="nuvemshop", external_store_id="98765",
            status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(
            user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(
            user=self.analyst, tenant=self.tenant, role=TenantMembership.Role.ANALYST)
        TenantMembership.objects.create(
            user=self.other_user, tenant=self.other, role=TenantMembership.Role.OWNER)
        self.installed = NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="12345", store_id="54321",
            token_ciphertext="encrypted-test-value-never-expose",
            scope="read_orders",
        )

    def payload(self, **changes):
        value = {
            "store_id": 54321,
            "event": "order/paid",
            "id": 87412,
            "event_launch_ts": 1794420000,
            "customer": {"email": "private@example.invalid"},
            "token": "never-store",
        }
        value.update(changes)
        return value

    def send(self, kind="paid", payload=None, *,
             signature=True, content_type="application/json", body=None):
        if body is None:
            body = json.dumps(payload if payload is not None else self.payload()).encode()
        sent = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse("nuvemshop-order-webhook", kwargs={"kind": kind}),
            data=body, content_type=content_type, secure=True,
            **({"HTTP_X_LINKEDSTORE_HMAC_SHA256": sent} if signature else {}),
        )

    def test_authenticated_receipt_is_minimal_and_money_never_moves(self):
        response = self.send()
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json(), {"received": True})
        event = OrderWebhookEvent.objects.get()
        self.assertEqual(event.tenant, self.tenant)
        self.assertEqual(event.store_id, "54321")
        self.assertEqual(event.order_id, "87412")
        self.assertEqual(event.topic, "order/paid")
        self.assertEqual(event.event_launch_ts, 1794420000)
        for private in ("private@example.invalid", "never-store", "customer"):
            self.assertNotIn(private, str(event.__dict__))
            self.assertNotIn(private, response.content.decode())
        self.assertEqual(CashbackEvent.objects.count(), 0)
        self.assertEqual(CashbackEntry.objects.count(), 0)

    def test_official_payload_without_optional_timestamp_is_accepted_and_coalesced(self):
        # Em documentação oficial o timestamp é enviado na maioria, mas não
        # em todos os webhooks. A inbox não deve transformar ausência em erro.
        basic = {"store_id": 54321, "event": "order/paid", "id": 87412}
        self.assertEqual(self.send(payload=basic).status_code, 202)
        receipt = OrderWebhookEvent.objects.get()
        self.assertIsNone(receipt.event_launch_ts)
        # Contadores arbitrários não podem burlar a deduplicação semântica.
        self.assertEqual(self.send(payload={**basic, "retry_count": 7}).status_code, 202)
        self.assertEqual(OrderWebhookEvent.objects.count(), 1)
        # Um tópico distinto ainda é conferível separadamente.
        self.assertEqual(self.send(
            kind="updated", payload={**basic, "event": "order/updated"},
        ).status_code, 202)
        self.assertEqual(OrderWebhookEvent.objects.count(), 2)
        self.assertFalse(CashbackEvent.objects.exists())
        self.assertFalse(CashbackEntry.objects.exists())

    def test_timestamp_only_malformed_is_rejected(self):
        for invalid in (None, False, True, -1, "oops", [], {}):
            with self.subTest(invalid=invalid):
                response = self.send(payload=self.payload(event_launch_ts=invalid))
                self.assertEqual(response.status_code, 400)
        self.assertFalse(OrderWebhookEvent.objects.exists())

    def test_retries_and_message_attributes_are_one_notification(self):
        self.assertEqual(self.send().status_code, 202)
        modified = self.payload(retry_count=19, nonce="second-delivery",
                                customer={"email": "changed@example.invalid"})
        self.assertEqual(self.send(payload=modified).status_code, 202)
        self.assertEqual(OrderWebhookEvent.objects.count(), 1)
        self.assertEqual(self.send(payload=self.payload(event_launch_ts=1794420001)).status_code, 202)
        self.assertEqual(OrderWebhookEvent.objects.count(), 2)
        updated = self.payload(event="order/updated", retry_count=3)
        self.assertEqual(self.send(kind="updated", payload=updated).status_code, 202)
        self.assertEqual(OrderWebhookEvent.objects.count(), 3)
        self.assertFalse(CashbackEvent.objects.exists())

    def test_valid_hmac_is_required_before_json_and_size_checks(self):
        self.assertEqual(self.send(signature=False).status_code, 401)
        self.assertEqual(self.send(body=b"not-json").status_code, 400)
        self.assertEqual(self.send(body=b"x" * 65537).status_code, 413)
        self.assertEqual(self.send(content_type="text/plain").status_code, 415)
        self.assertEqual(self.send(payload=self.payload(event="order/updated")).status_code, 400)
        self.assertEqual(self.send(payload=self.payload(event_launch_ts=None)).status_code, 400)
        self.assertEqual(self.send(payload=self.payload(event_launch_ts=True)).status_code, 400)
        self.assertEqual(self.send(payload=self.payload(id="invalid")).status_code, 400)
        self.assertEqual(self.send(payload=self.payload(store_id=-1)).status_code, 400)
        self.assertFalse(OrderWebhookEvent.objects.exists())
        with patch.dict(os.environ, {"NUVEMSHOP_CLIENT_SECRET": ""}):
            self.assertEqual(self.send().status_code, 503)

    def test_installation_scope_and_tenant_boundaries(self):
        self.assertEqual(self.send(payload=self.payload(store_id=999999)).status_code, 202)
        self.assertEqual(self.send(payload=self.payload(store_id=98765)).status_code, 202)
        self.assertFalse(OrderWebhookEvent.objects.exists())
        self.installed.scope = "read_products"
        self.installed.save(update_fields=["scope"])
        self.assertEqual(self.send().status_code, 202)
        self.assertFalse(OrderWebhookEvent.objects.exists())
        self.installed.scope = "read_orders"
        self.installed.client_id = "88888"
        self.installed.save(update_fields=["scope", "client_id"])
        self.assertEqual(self.send().status_code, 202)
        self.assertFalse(OrderWebhookEvent.objects.exists())
        self.installed.client_id = "12345"
        self.installed.save(update_fields=["client_id"])
        self.tenant.status = Tenant.Status.SUSPENDED
        self.tenant.save(update_fields=["status"])
        self.assertEqual(self.send().status_code, 202)
        self.assertFalse(OrderWebhookEvent.objects.exists())

    def test_disabled_switch_blocks_even_valid_signed_events(self):
        with override_settings(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=False):
            self.assertEqual(self.send().status_code, 503)
        self.assertFalse(OrderWebhookEvent.objects.exists())

    def test_database_failure_returns_retryable_response_without_ack(self):
        with patch(
            "apps.nuvemshop.order_webhooks.OrderWebhookEvent.objects.get_or_create",
            side_effect=RuntimeError("sensitive-error-must-not-leak"),
        ):
            with self.assertLogs("apps.nuvemshop.order_webhooks", level="WARNING") as logs:
                response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("sensitive-error-must-not-leak", " ".join(logs.output))
        self.assertFalse(OrderWebhookEvent.objects.exists())

    def test_only_own_admin_can_inspect_event_receipts(self):
        self.assertEqual(self.send().status_code, 202)
        path = reverse("nuvemshop-order-events", kwargs={"tenant_id": self.tenant.pk})
        self.client.force_login(self.owner)
        response = self.client.get(path, secure=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(response.json()["items"][0]["state"], "pending_reconciliation")
        self.assertFalse(response.json()["cashback_credited"])
        self.assertNotIn("private@example.invalid", response.content.decode())
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.get(path, secure=True).status_code, 403)
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(path, secure=True).status_code, 404)
        self.client.force_login(self.owner)
        with override_settings(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=False):
            self.assertEqual(self.client.get(path, secure=True).status_code, 409)
