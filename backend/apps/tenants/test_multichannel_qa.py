"""QA sem dependência do nome da loja ou de uma plataforma de e-commerce.

Os testes nunca enviam cupons nem escrevem pontos financeiros.
"""
import io
import json
import os
import secrets
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase

from apps.core.auth_views import _public_tenants
from apps.tenants.models import Tenant, TenantMembership, TenantLoyaltyActivationAudit


class MultichannelPilotTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="qa-multichannel-owner",
            email="qa-merchant@example.invalid",
            password=secrets.token_hex(16),
        )
        self.tenant = Tenant.objects.create(
            name="Bibelô - Ambiente de Teste",
            slug="qa-bibelo-isolado",
            platform="independent",
            status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner")
        self.env = {
            "FIDELIZA_ENVIRONMENT": "homolog",
            "FIDELIZA_PILOT_ACTIVATION_APPROVAL": "YES_VERIFIED_QA_ONLY",
            "FIDELIZA_DEPLOYED_SHA": "a" * 40,
        }
        self.opts = {
            "tenant_id": str(self.tenant.pk),
            "actor_id": str(self.user.pk),
            "ticket": "QA-MULTICHANNEL-2026",
            "approved_sha": "a" * 40,
        }

    def test_session_tenant_exposes_independent_platform(self):
        record = _public_tenants(self.user)[0]
        self.assertEqual(record["platform"], "independent")
        self.assertEqual(record["slug"], "qa-bibelo-isolado")

    def test_independent_qa_report_does_not_require_nuvemshop_oauth(self):
        out = io.StringIO()
        with patch.dict(os.environ, self.env):
            call_command(
                "set_loyalty_release", mode="qa", dry_run=True,
                confirm="ENABLE_QA_ONLY", stdout=out, **self.opts,
            )
        data = json.loads(out.getvalue())
        self.assertEqual(data["status"], "READY_FOR_HOMOLOG_ACTIVATION")
        self.assertEqual(data["commercial_status"], "NO_GO_COMMERCIAL")
        self.assertFalse(data["checks"]["oauth_installed"])
        self.assertTrue(data["checks"]["oauth_optional_for_independent_qa"])
        self.assertTrue(data["checks"]["financial_gates_off"])
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.loyalty_live_enabled)

    def test_controlled_qa_activation_is_not_brand_specific(self):
        with patch.dict(os.environ, self.env):
            call_command(
                "set_loyalty_pilot", enable=True,
                confirm="ENABLE_QA_ONLY", **self.opts,
                stdout=io.StringIO(),
            )
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.loyalty_live_enabled)
        self.assertEqual(
            TenantLoyaltyActivationAudit.objects.filter(tenant=self.tenant).count(), 1,
        )
        with patch.dict(os.environ, self.env):
            call_command(
                "set_loyalty_pilot", disable=True,
                confirm="DISABLE_QA_ONLY", **self.opts,
                stdout=io.StringIO(),
            )
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.loyalty_live_enabled)

    def test_pilot_rejects_production_environment_and_nonqa_tenant(self):
        with patch.dict(os.environ, {**self.env, "FIDELIZA_ENVIRONMENT": "production"}):
            with self.assertRaisesRegex(CommandError, "homologação"):
                call_command(
                    "set_loyalty_pilot", enable=True,
                    confirm="ENABLE_QA_ONLY", **self.opts,
                )
        self.tenant.slug = "bibeloo-prod"
        self.tenant.save(update_fields=["slug"])
        with patch.dict(os.environ, self.env):
            with self.assertRaisesRegex(CommandError, "criado para QA"):
                call_command(
                    "set_loyalty_pilot", enable=True,
                    confirm="ENABLE_QA_ONLY", **self.opts,
                )

    def test_commercial_dry_run_never_approves_independent_qa(self):
        out = io.StringIO()
        with patch.dict(os.environ, self.env):
            call_command(
                "set_loyalty_release", mode="commercial", dry_run=True,
                confirm="ENABLE_COMMERCIAL", stdout=out, **self.opts,
            )
        data = json.loads(out.getvalue())
        self.assertEqual(data["status"], "NOT_READY_FOR_HOMOLOG_ACTIVATION")
        self.assertEqual(data["commercial_status"], "NO_GO_COMMERCIAL")
