"""Cadastro automático dos avisos de pedido: só cria o que falta, nunca apaga, nunca fora de HTTPS,
não roda com receptor desligado ou sem permissão de pedidos. A Nuvemshop é simulada."""
import io
import json
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from .webhook_setup import WebhookSetupError, order_webhooks, receiver_url

CALLBACK = "https://api.loja.example/api/v1/oauth/nuvemshop/callback/"
PAID = "https://api.loja.example/api/v1/webhooks/orders/paid/"
UPDATED = "https://api.loja.example/api/v1/webhooks/orders/updated/"
STORE = SimpleNamespace(pk="tenant-qa")


class Response:
    def __init__(self, status, body):
        self.status, self.body = status, json.dumps(body).encode()

    def read(self, _limit):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeStore:
    """Opener falso: guarda as chamadas e responde como a API de webhooks."""
    def __init__(self, existing=None, empty_404=False):
        self.hooks = list(existing or [])
        self.calls = []
        self.empty_404 = empty_404

    def open(self, request, timeout):
        self.calls.append((request.get_method(), request.full_url))
        if request.get_method() == "GET":
            if self.empty_404 and not self.hooks:
                raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b'{"description":"Last page is 0"}'))
            return Response(200, self.hooks)
        payload = json.loads(request.data)
        hook = {"id": len(self.hooks) + 1, **payload}
        self.hooks.append(hook)
        return Response(201, hook)


def creds(scope="read_orders,write_coupons"):
    return mock.patch("apps.nuvemshop.webhook_setup._credentials",
                      return_value=("555", "t" * 32, "Vidalys Fideliza (qa@example.invalid)", CALLBACK, scope))


@override_settings(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True)
class OrderWebhookSetupTests(SimpleTestCase):
    def test_receiver_url_comes_from_api_callback_and_requires_https(self):
        self.assertEqual(receiver_url(CALLBACK, "paid"), PAID)
        with self.assertRaises(WebhookSetupError):
            receiver_url("http://api.loja.example/api/v1/oauth/nuvemshop/callback/", "paid")

    def test_creates_only_missing_and_keeps_third_party_hooks(self):
        store = FakeStore(existing=[{"id": 9, "event": "order/paid", "url": PAID},
                                    {"id": 10, "event": "order/created", "url": "https://outro-app.example/hook"}])
        with creds():
            result = order_webhooks(STORE, ensure=True, opener=store)
        self.assertEqual(result, {"order/paid": "ok", "order/updated": "created"})
        self.assertEqual([m for m, _ in store.calls], ["GET", "POST"])        # nenhum DELETE
        self.assertIn({"id": 3, "event": "order/updated", "url": UPDATED}, store.hooks)
        with creds():
            again = order_webhooks(STORE, ensure=True, opener=store)      # idempotente
        self.assertEqual(again, {"order/paid": "ok", "order/updated": "ok"})

    def test_empty_store_answering_404_last_page_creates_both(self):
        store = FakeStore(empty_404=True)
        with creds():
            self.assertEqual(order_webhooks(STORE, ensure=True, opener=store),
                             {"order/paid": "created", "order/updated": "created"})

    def test_check_only_reports_missing_without_creating(self):
        store = FakeStore()
        with creds():
            self.assertEqual(order_webhooks(STORE, opener=store),
                             {"order/paid": "missing", "order/updated": "missing"})
        self.assertEqual([m for m, _ in store.calls], ["GET"])

    def test_skips_without_order_scope_or_with_receiver_off(self):
        store = FakeStore()
        with creds(scope="read_products"):
            self.assertEqual(order_webhooks(STORE, ensure=True, opener=store), {"_skipped": "no_order_scope"})
        with override_settings(FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=False):
            self.assertEqual(order_webhooks(STORE, ensure=True, opener=store), {"_skipped": "receiver_off"})
        self.assertEqual(store.calls, [])

    def test_provider_error_is_raised_not_hidden(self):
        class Down:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 500, "Error", {}, io.BytesIO(b""))
        with creds(), self.assertRaises(WebhookSetupError):
            order_webhooks(STORE, ensure=True, opener=Down())
