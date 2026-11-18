"""Recompensas criadas no painel valem na loja online das lojas Nuvemshop."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from .models import DiscountRewardDraft


@override_settings(FIDELIZA_POINTS_WRITES_ENABLED=False, FIDELIZA_LEDGER_WRITES_ENABLED=False)
class RewardChannelsTests(TestCase):
    def _owner_of(self, platform, slug, store_id=""):
        user = get_user_model().objects.create_user(username="dono-" + slug)
        tenant = Tenant.objects.create(name="Loja " + slug, slug=slug, platform=platform,
                                       external_store_id=store_id, status=Tenant.Status.ACTIVE)
        TenantMembership.objects.create(user=user, tenant=tenant, role=TenantMembership.Role.OWNER)
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        client.get(reverse("auth-session"))
        return tenant, client

    def _create(self, tenant, client):
        return client.post(
            reverse("discount-reward-drafts", kwargs={"tenant_id": tenant.id}),
            {"title": "R$ 10 de desconto", "points_cost": 500, "discount_cents": 1000,
             "min_order_cents": 5000, "max_redemptions": 50},
            format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

    def test_nuvemshop_store_reward_includes_online_channel(self):
        tenant, client = self._owner_of("nuvemshop", "canal-online", "880011")
        response = self._create(tenant, client)
        self.assertEqual(response.status_code, 201)
        reward = DiscountRewardDraft.objects.get(tenant=tenant)
        self.assertEqual(reward.allowed_channels.split(","), ["nuvemshop", "counter", "vidalys_flow"])
        self.assertFalse(response.json()["coupon_created"])

    def test_independent_store_keeps_counter_channels(self):
        tenant, client = self._owner_of("independent", "canal-balcao")
        self.assertEqual(self._create(tenant, client).status_code, 201)
        reward = DiscountRewardDraft.objects.get(tenant=tenant)
        self.assertNotIn("nuvemshop", reward.allowed_channels.split(","))
