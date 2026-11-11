"""Configurações editáveis por lojista; testam papéis, versões e isolamento."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.branding_models import TenantBranding, TenantBrandingAudit
from apps.tenants.models import Tenant, TenantMembership


class TenantSettingsTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user(username="settings-owner")
        self.admin=User.objects.create_user(username="settings-admin")
        self.analyst=User.objects.create_user(username="settings-analyst")
        self.other=User.objects.create_user(username="settings-other")
        self.tenant=Tenant.objects.create(name="Loja Vila",slug="loja-vila")
        self.foreign=Tenant.objects.create(name="Loja Centro",slug="loja-centro")
        for user,tenant,role in (
            (self.owner,self.tenant,"owner"),
            (self.admin,self.tenant,"admin"),
            (self.analyst,self.tenant,"analyst"),
            (self.other,self.foreign,"owner"),
        ):
            TenantMembership.objects.create(user=user,tenant=tenant,role=role)
        self.client=APIClient()
        self.client.force_authenticate(self.owner)
        self.endpoint=reverse("tenant-settings",kwargs={"tenant_id":self.tenant.pk})
        self.body={
            "program_name":"Clube da Vila",
            "primary_color":"#087F79",
            "accent_color":"#37D5BB",
            "support_email":"atendimento@example.invalid",
            "expected_version":0,
        }

    def test_settings_start_without_fake_publication(self):
        response=self.client.get(self.endpoint)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["version"],0)
        self.assertEqual(response.data["branding"]["program_name"],"Clube Loja Vila")
        self.assertIsNone(response.data["public_link"])
        self.assertFalse(response.data["features"]["cashback_activation_enabled"])
        self.assertFalse(response.data["features"]["custom_domain_available"])
        self.assertNotIn("token",str(response.data))
        self.assertEqual(response["Cache-Control"],"private, no-store")
        self.assertFalse(TenantBranding.objects.exists())

    def test_owner_can_edit_with_versioned_audit_and_no_membership_side_effects(self):
        response=self.client.patch(self.endpoint,self.body,format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data["updated"])
        self.assertEqual(response.data["version"],1)
        branding=TenantBranding.objects.get(tenant=self.tenant)
        self.assertEqual(branding.program_name,"Clube da Vila")
        self.assertEqual(branding.support_email,"atendimento@example.invalid")
        self.assertEqual(branding.updated_by,self.owner)
        audit=TenantBrandingAudit.objects.get()
        self.assertEqual(audit.version,1)
        self.assertEqual(audit.actor,self.owner)
        self.assertEqual(audit.before["program_name"],"")
        self.assertEqual(audit.after["program_name"],"Clube da Vila")
        self.assertEqual(TenantMembership.objects.count(),4)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status,"draft")

        repeat=self.client.patch(
            self.endpoint,{**self.body,"expected_version":1},format="json"
        )
        self.assertEqual(repeat.status_code,200)
        self.assertFalse(repeat.data["updated"])
        self.assertEqual(TenantBrandingAudit.objects.count(),1)
        stale=self.client.patch(self.endpoint,self.body,format="json")
        self.assertEqual(stale.status_code,409)
        self.assertEqual(stale.data["current_version"],1)

        revised=self.client.patch(self.endpoint,{
            **self.body,"expected_version":1,
            "program_name":"Clube Vila renovado",
        },format="json")
        self.assertEqual(revised.status_code,200,revised.data)
        self.assertEqual(revised.data["version"],2)
        self.assertEqual(TenantBrandingAudit.objects.count(),2)

    def test_admin_can_edit_but_analyst_cannot(self):
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get(self.endpoint).status_code,200)
        self.assertFalse(self.client.get(self.endpoint).data["can_edit"])
        self.assertEqual(self.client.patch(self.endpoint,self.body,format="json").status_code,403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(self.endpoint,self.body,format="json").status_code,200)

    def test_tenant_isolation_and_unauthenticated(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.endpoint).status_code,404)
        self.assertEqual(self.client.patch(self.endpoint,self.body,format="json").status_code,404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.endpoint).status_code,(401,403))
        self.assertIn(self.client.patch(self.endpoint,self.body,format="json").status_code,(401,403))
        self.assertFalse(TenantBranding.objects.exists())

    def test_invalid_payload_cannot_insert_css_html_or_extra_fields(self):
        bad=[
            {**self.body,"primary_color":"#FFFFFF"},
            {**self.body,"primary_color":"red"},
            {**self.body,"primary_color":"#000000; background:url(https://bad.invalid)"},
            {**self.body,"program_name":"A"},
            {**self.body,"program_name":"Loja\nmaliciosa"},
            {**self.body,"support_email":"invalido"},
            {**self.body,"expected_version":True},
            {**self.body,"program_id":"another-tenant"},
            {**self.body,"customer_id":"123"},
        ]
        for item in bad:
            with self.subTest(item=item):
                self.assertEqual(self.client.patch(self.endpoint,item,format="json").status_code,400)
        self.assertFalse(TenantBranding.objects.exists())
        self.assertFalse(TenantBrandingAudit.objects.exists())

    def test_values_are_private_to_their_tenant(self):
        self.client.patch(self.endpoint,self.body,format="json")
        self.client.force_authenticate(self.other)
        foreign=reverse("tenant-settings",kwargs={"tenant_id":self.foreign.pk})
        answer=self.client.get(foreign)
        self.assertEqual(answer.status_code,200)
        self.assertNotIn("Clube da Vila",str(answer.data))
        self.assertEqual(answer.data["branding"]["program_name"],"Clube Loja Centro")
