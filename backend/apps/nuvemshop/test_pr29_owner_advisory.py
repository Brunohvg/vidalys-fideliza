"""PR29: read-only merchant diagnostic must never authorize store discounts."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from apps.tenants.models import Tenant, TenantMembership
from .coupon_client import coupon_payload
from django.utils import timezone
from datetime import timedelta


class CouponOwnerAdvisoryTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username="pr29-advisory-owner")
        self.tenant=Tenant.objects.create(
            name="Shop owner QA",slug="pr29-advisory",
            platform="nuvemshop",external_store_id="54321",
        )
        TenantMembership.objects.create(
            tenant=self.tenant,user=self.user,role=TenantMembership.Role.OWNER,
        )
        self.url=reverse("nuvemshop-coupon-owner-advisory")
        self.payload={
            "tenant_id":str(self.tenant.pk),
            "coupon_id":"876","customer_id":"700",
        }

    def test_default_flags_and_coupon_payload_have_no_unverified_owner_binding(self):
        self.assertFalse(self.tenant.loyalty_live_enabled)
        payload=coupon_payload(
            code="VF"+"A"*24,discount_cents=100,min_order_cents=1000,
            expires_at=timezone.now()+timedelta(days=2),
        )
        self.assertNotIn("customer_id",payload)

    def test_anonymous_storefront_cannot_query_owner(self):
        result=self.client.post(self.url,self.payload,content_type="application/json")
        self.assertIn(result.status_code,(401,403))

    def test_merchant_lookups_are_advisory_only_and_non_authoritative(self):
        self.client.force_login(self.user)
        result=self.client.post(self.url,self.payload,content_type="application/json")
        self.assertEqual(result.status_code,200,result.content)
        self.assertFalse(result.json()["matched"])
        self.assertFalse(result.json()["may_apply_discount"])
        self.assertFalse(result.json()["preventive_checkout_enforced"])
        self.assertEqual(result.json()["mode"],"advisory_only")
        self.assertEqual(result["Cache-Control"],"private, no-store")

    def test_invalid_or_unknown_store_denied(self):
        self.client.force_login(self.user)
        for payload,status in (
            ({**self.payload,"tenant_id":"invalid"},400),
            ({**self.payload,"coupon_id":"x"},400),
            ({**self.payload,"extra":True},400),
        ):
            with self.subTest(payload=payload):
                result=self.client.post(self.url,payload,content_type="application/json")
                self.assertEqual(result.status_code,status)
