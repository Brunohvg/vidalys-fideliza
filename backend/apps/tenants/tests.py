from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Tenant, TenantMembership

class TenantIsolationTests(TestCase):
    def setUp(self):
        self.alice = get_user_model().objects.create_user(username="alice", password="test-pass-for-ci")
        self.bob = get_user_model().objects.create_user(username="bob", password="test-pass-for-ci")
        a = Tenant.objects.create(name="Loja A", slug="loja-a", external_store_id="store-A")
        b = Tenant.objects.create(name="Loja B", slug="loja-b", external_store_id="store-B")
        TenantMembership.objects.create(tenant=a, user=self.alice, role="owner")
        TenantMembership.objects.create(tenant=b, user=self.bob, role="analyst")

    def test_guest_blocked(self):
        self.assertIn(self.client.get(reverse("my-tenants")).status_code, (401, 403))

    def test_isolation(self):
        self.client.force_login(self.alice)
        result = self.client.get(reverse("my-tenants"))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()["results"]), 1)
        self.assertEqual(result.json()["results"][0]["name"], "Loja A")
        self.assertNotIn("Loja B", str(result.json()))

    def test_no_membership(self):
        nobody = get_user_model().objects.create_user(username="nobody", password="test-pass-for-ci")
        self.client.force_login(nobody)
        self.assertEqual(self.client.get(reverse("my-tenants")).json()["results"], [])
