"""app/uninstalled e avisos de cancelamento: sem apagar, creditar ou estornar."""
import hashlib
import hmac
import json
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation
from .order_webhook_models import OrderWebhookEvent

SECRET = "synthetic-hmac-secret-for-lifecycle"


@override_settings(
    FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class AppLifecycleWebhookTests(TestCase):
    def setUp(self):
        context = patch.dict(os.environ, {
            "NUVEMSHOP_CLIENT_ID": "12345",
            "NUVEMSHOP_CLIENT_SECRET": SECRET,
        })
        context.start()
        self.addCleanup(context.stop)
        self.client = Client(enforce_csrf_checks=True)
        self.owner = get_user_model().objects.create_user(username="lifecycle-owner")
        self.tenant = Tenant.objects.create(
            name="Ciclo piloto", slug="ciclo-piloto", platform="nuvemshop",
            external_store_id="54321", status=Tenant.Status.ACTIVE,
        )
        self.other = Tenant.objects.create(
            name="Ciclo outro", slug="ciclo-outro", platform="nuvemshop",
            external_store_id="98765", status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(
            user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        self.installed = NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="12345", store_id="54321",
            token_ciphertext="encrypted-test-value", scope="read_orders",
        )
        self.foreign = NuvemshopInstallation.objects.create(
            tenant=self.other, client_id="12345", store_id="98765",
            token_ciphertext="encrypted-other-value", scope="read_orders",
        )

    def post(self, name, kind, payload, *, signed=True):
        body = json.dumps(payload).encode()
        signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse(name, kwargs={"kind": kind}), data=body,
            content_type="application/json", secure=True,
            **({"HTTP_X_LINKEDSTORE_HMAC_SHA256": signature} if signed else {}),
        )

    def uninstall(self, store_id=54321, **options):
        return self.post("nuvemshop-app-webhook", "uninstalled",
                         {"store_id": store_id, "event": "app/uninstalled"}, **options)

    def test_uninstall_requires_valid_signature(self):
        self.assertEqual(self.uninstall(signed=False).status_code, 401)
        self.installed.refresh_from_db()
        self.assertIsNone(self.installed.uninstalled_at)

    def test_unknown_kind_and_bad_payload_are_rejected(self):
        response = self.post("nuvemshop-app-webhook", "suspended",
                             {"store_id": 54321, "event": "app/suspended"})
        self.assertEqual(response.status_code, 404)
        response = self.post("nuvemshop-app-webhook", "uninstalled",
                             {"store_id": "abc", "event": "app/uninstalled"})
        self.assertEqual(response.status_code, 400)

    def test_uninstall_marks_only_that_store_and_is_idempotent(self):
        self.assertEqual(self.uninstall().status_code, 202)
        self.installed.refresh_from_db()
        first = self.installed.uninstalled_at
        self.assertIsNotNone(first)
        self.assertFalse(self.installed.active)
        self.assertEqual(self.uninstall().status_code, 202)
        self.installed.refresh_from_db()
        self.assertEqual(self.installed.uninstalled_at, first)
        self.foreign.refresh_from_db()
        self.assertIsNone(self.foreign.uninstalled_at)
        # Nada é apagado: a limpeza continua sendo papel do store/redact.
        self.assertTrue(NuvemshopInstallation.objects.filter(pk=self.installed.pk).exists())

    def test_uninstalled_store_stops_receiving_order_events(self):
        self.uninstall()
        response = self.post("nuvemshop-order-webhook", "paid", {
            "store_id": 54321, "event": "order/paid", "id": 777,
            "event_launch_ts": 1794420000,
        })
        self.assertEqual(response.status_code, 202)
        self.assertFalse(OrderWebhookEvent.objects.exists())

    def test_cancelled_and_voided_enter_inbox_without_financial_effect(self):
        for kind, topic in (("cancelled", "order/cancelled"), ("voided", "order/voided")):
            response = self.post("nuvemshop-order-webhook", kind, {
                "store_id": 54321, "event": topic, "id": 888,
                "event_launch_ts": 1794420001,
            })
            self.assertEqual(response.status_code, 202)
        topics = set(OrderWebhookEvent.objects.values_list("topic", flat=True))
        self.assertEqual(topics, {"order/cancelled", "order/voided"})

    def test_topic_must_match_route(self):
        response = self.post("nuvemshop-order-webhook", "cancelled", {
            "store_id": 54321, "event": "order/paid", "id": 889,
        })
        self.assertEqual(response.status_code, 400)

    def test_status_reports_reinstall_after_uninstall(self):
        self.client.force_login(self.owner)
        url = reverse("nuvemshop-status", kwargs={"tenant_id": self.tenant.pk})
        with patch.dict(os.environ, {
            "NUVEMSHOP_TOKEN_KEYS": "x" * 44,
            "NUVEMSHOP_OAUTH_CALLBACK_URL": "https://testserver/api/v1/oauth/nuvemshop/callback/",
            "NUVEMSHOP_API_USER_AGENT": "Fideliza QA (qa@example.invalid)",
        }), patch("apps.nuvemshop.views.config") as cfg:
            cfg.return_value.client_id = "12345"
            before = self.client.get(url, secure=True).json()
            self.uninstall()
            after = self.client.get(url, secure=True).json()
        self.assertTrue(before["connected"])
        self.assertIsNone(before["uninstalled_at"])
        self.assertFalse(after["connected"])
        self.assertIsNotNone(after["uninstalled_at"])
        self.assertEqual(after["connection_check"]["next_step"], "reinstall_app")
        self.assertNotIn("encrypted-test-value", json.dumps(after))
