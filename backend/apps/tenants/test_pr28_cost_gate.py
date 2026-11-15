"""PR28: 100% live sellable variant cost coverage and commercial command gate."""
import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.costs.catalog_gate import verify_active_catalog_costs, CatalogCostCoverageBlocked
from apps.costs.models import CostItem
from apps.tenants.models import Tenant


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"pagarme_v5"}),
    FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True,
    FIDELIZA_PREISSUE_OWNERSHIP_CHECK_ENABLED=True,
    FIDELIZA_CHECKOUT_OWNER_ENFORCEMENT_VERIFIED=True,
)
class CompleteCatalogGateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="pr28-catalog-admin", email="pr28@example.invalid",
            password="synthetic-not-for-live",
        )
        self.tenant = Tenant.objects.create(
            name="QA cost check", slug="qa-pr28-cost",
            status=Tenant.Status.ACTIVE, platform="nuvemshop",
            external_store_id="54321",
        )
        self.products = [
            {"id":101, "visibility":"visible", "published":True,
             "variants":[{"id":201, "sku":"ABC-01"}]},
            # Buyable via direct URL even though published=False.
            {"id":102, "visibility":"unlisted", "published":False,
             "variants":[{"id":202, "sku":"ABC-02"}]},
            {"id":103, "visibility":"hidden", "published":False,
             "variants":[{"id":203, "sku":"HIDDEN-03"}]},
        ]
        self.env = {
            "FIDELIZA_ENVIRONMENT":"production",
            "FIDELIZA_COMMERCIAL_GO_LIVE_APPROVED":"YES_RELEASE_REVIEWED",
            "FIDELIZA_COMMERCIAL_ALLOWED_TENANT_ID":str(self.tenant.pk),
            "FIDELIZA_DEPLOYED_SHA":"a"*40,
        }
        self.options = {
            "mode":"commercial", "tenant_id":str(self.tenant.pk),
            "actor_id":str(self.user.pk), "ticket":"PR28-CATALOG-QA",
            "approved_sha":"a"*40, "enable":True,
            "confirm":"ENABLE_COMMERCIAL",
        }

    def _cost(self, variant_id, sku):
        return CostItem.objects.create(
            tenant=self.tenant, reference="REF-" + sku, sku=sku,
            external_variant_id=str(variant_id), name="Produto " + sku,
            unit_cost_cents=100, selling_price_cents=300,
            verified_at=timezone.now(), verified_by=self.user,
        )

    def _command(self):
        with (
            patch.dict(os.environ, self.env),
            patch("apps.tenants.management.commands.set_loyalty_release.verify_postgres_immutability"),
            patch("apps.tenants.management.commands.set_loyalty_release.check_rule_and_costs"),
            patch("apps.tenants.management.commands.set_loyalty_release.check_oauth",
                  return_value=("54321", "synthetic-token", "Synthetic App QA")),
            patch("apps.costs.catalog_gate.read_products_page", side_effect=[self.products]),
        ):
            return call_command("set_loyalty_release", **self.options)

    def test_command_rejects_partially_verified_active_catalog(self):
        self._cost(201, "ABC-01")
        with self.assertRaisesRegex(CommandError, "SKU ativo sem custo verificado"):
            self._command()
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.loyalty_live_enabled)

    def test_command_accepts_exact_complete_catalog_with_explicit_test_gates(self):
        self._cost(201, "ABC-01")
        self._cost(202, "ABC-02")
        self._command()
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.loyalty_live_enabled)

    def test_wrong_sku_on_existing_variant_is_not_a_verified_cost(self):
        self._cost(201, "WRONG")
        self._cost(202, "ABC-02")
        with self.assertRaises(CatalogCostCoverageBlocked):
            with patch("apps.costs.catalog_gate.read_products_page", return_value=self.products):
                verify_active_catalog_costs(
                    tenant=self.tenant, store_id="54321", token="synthetic",
                    user_agent="Synthetic QA",
                )

    def test_incomplete_catalog_scan_cannot_pass_and_still_excludes_hidden(self):
        self._cost(201, "ABC-01")
        self._cost(202, "ABC-02")
        with patch("apps.costs.catalog_gate.read_products_page", return_value=self.products):
            self.assertEqual(verify_active_catalog_costs(
                tenant=self.tenant, store_id="54321", token="synthetic",
                user_agent="Synthetic QA",
            ), 2)
        bad = [{"id":100, "published":False,
                "variants":[{"id":202,"sku":"ABC-02"}]}]
        with patch("apps.costs.catalog_gate.read_products_page", return_value=bad):
            with self.assertRaisesRegex(CatalogCostCoverageBlocked, "Visibilidade"):
                verify_active_catalog_costs(
                    tenant=self.tenant, store_id="54321", token="synthetic",
                    user_agent="Synthetic QA",
                )
