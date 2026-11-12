"""Pré-voo de homologação: leitura segura sem prometer cashback real."""
import json
from django.test import TestCase,override_settings

from apps.nuvemshop.models import NuvemshopInstallation
from apps.tenants.models import Tenant
from scripts.inspect_loyalty_journey import inspect


class JourneyPreflightTests(TestCase):
    def setUp(self):
        self.tenant=Tenant.objects.create(
            name="Loja de teste",slug="journey-lab",
            status=Tenant.Status.ACTIVE,
            platform="nuvemshop",external_store_id="123",
        )

    def test_readonly_preflight_reports_only_verified_capabilities(self):
        before=self.tenant.updated_at
        result=inspect("journey-lab")
        self.assertEqual(result["nuvemshop_connected"],False)
        self.assertEqual(result["program_terms_approved"],False)
        self.assertEqual(result["active_participants_count"],0)
        self.assertFalse(result["live_cashback_granting_available"])
        self.assertFalse(result["paid_order_verification_available"])
        self.assertFalse(result["live_redemption_available"])
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.updated_at,before)

    @override_settings(
        FIDELIZA_PUBLIC_SIGNUP_ENABLED=True,
        FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
        FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True,
        FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=True,
    )
    def test_flags_dont_claim_delivery_or_payments_and_no_secret_leaks(self):
        NuvemshopInstallation.objects.create(
            tenant=self.tenant,client_id="456",store_id="123",
            token_ciphertext="encrypted-secret-never-output",
            scope="read_products,read_customers",
        )
        result=inspect("journey-lab")
        self.assertTrue(result["nuvemshop_connected"])
        self.assertTrue(result["products_read_permission_recorded"])
        self.assertTrue(result["customers_read_permission_recorded"])
        self.assertTrue(result["public_signup_enabled"])
        self.assertTrue(result["email_delivery_flag_enabled"])
        self.assertTrue(result["customer_approval_enabled"])
        self.assertFalse(result["live_cashback_granting_available"])
        exported=json.dumps(result)
        self.assertNotIn("encrypted-secret",exported)
        self.assertNotIn("read_customers",exported)
        self.assertNotIn("client_id",exported)
        self.assertNotIn("customer_id",exported)

    def test_does_not_mistake_wrong_store_installation_for_connection(self):
        NuvemshopInstallation.objects.create(
            tenant=self.tenant,client_id="456",store_id="987",
            token_ciphertext="encrypted-secret-never-output",
            scope="read_products",
        )
        self.assertFalse(inspect("journey-lab")["nuvemshop_connected"])
