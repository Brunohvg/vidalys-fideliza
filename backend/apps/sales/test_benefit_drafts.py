"""Proteções dos rascunhos: isolamento, limites e nenhuma ação externa."""
from django.contrib.auth import get_user_model
from django.test import TestCase,override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant,TenantMembership
from apps.wallets.models import CashbackWallet,CashbackEvent
from apps.points.models import PointWallet,PointEvent
from .models import DiscountRewardDraft,PointCampaignDraft


@override_settings(FIDELIZA_POINTS_WRITES_ENABLED=False,FIDELIZA_LEDGER_WRITES_ENABLED=False)
class BenefitDraftTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user(username="benefits-owner")
        self.analyst=User.objects.create_user(username="benefits-analyst")
        self.stranger=User.objects.create_user(username="benefits-stranger")
        self.tenant=Tenant.objects.create(
            name="Loja QA de recompensas",slug="loja-benefit-draft",
            platform="independent",status=Tenant.Status.ACTIVE,
        )
        self.foreign=Tenant.objects.create(
            name="Outra loja de recompensas",slug="loja-benefit-foreign",
            platform="independent",status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,user=self.owner,role=TenantMembership.Role.OWNER
        )
        TenantMembership.objects.create(
            tenant=self.tenant,user=self.analyst,role=TenantMembership.Role.ANALYST
        )
        self.client=APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.client.get(reverse("auth-session"))
        self.reward=reverse("discount-reward-drafts",kwargs={"tenant_id":self.tenant.id})
        self.campaign=reverse("point-campaign-drafts",kwargs={"tenant_id":self.tenant.id})
        self.reward_data={
            "title":"R$ 5 de desconto", "points_cost":200,
            "discount_cents":500,"min_order_cents":3000,
            "max_redemptions":50,
        }
        self.campaign_data={
            "goal":"second_purchase","bonus_points":20,"max_customers":40,
        }

    def send(self,url,data):
        self.client.get(reverse("auth-session"))
        return self.client.post(url,data,format="json",
             HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

    def assert_no_effects(self):
        self.assertFalse(PointWallet.objects.exists())
        self.assertFalse(PointEvent.objects.exists())
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    def test_create_reward_is_draft_and_never_generates_coupon_or_points(self):
        response=self.send(self.reward,self.reward_data)
        self.assertEqual(response.status_code,201,response.data)
        self.assertFalse(response.data["coupon_created"])
        self.assertFalse(response.data["points_credited"])
        self.assertFalse(response.data["reward"]["published"])
        self.assertFalse(response.data["reward"]["redemption_enabled"])
        self.assertEqual(self.client.get(self.reward).data["items"][0]["points_cost"],200)
        self.assertEqual(DiscountRewardDraft.objects.count(),1)
        self.assert_no_effects()

    def test_create_campaign_is_draft_and_never_sends_messages(self):
        response=self.send(self.campaign,self.campaign_data)
        self.assertEqual(response.status_code,201,response.data)
        self.assertFalse(response.data["messages_sent"])
        self.assertFalse(response.data["points_credited"])
        self.assertEqual(response.data["campaign"]["maximum_bonus_points"],800)
        self.assertFalse(response.data["campaign"]["published"])
        self.assertEqual(PointCampaignDraft.objects.count(),1)
        self.assert_no_effects()

    def test_insecure_reward_values_rejected(self):
        variants=[
            {"discount_cents":-1},{"discount_cents":True},
            {"discount_cents":5000,"min_order_cents":1000},
            {"points_cost":0},{"points_cost":True},
            {"max_redemptions":100001},{"title":"a"},
            {"published":True},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(self.send(self.reward,{
                    **self.reward_data,**variant,
                }).status_code,400)
        self.assertFalse(DiscountRewardDraft.objects.exists())
        self.assert_no_effects()

    def test_campaign_limits_rejected(self):
        variants=[
            {"bonus_points":0},{"bonus_points":True},
            {"max_customers":0},{"max_customers":True},
            {"bonus_points":100001},{"goal":"send_all_now"},
            {"bonus_points":100000,"max_customers":50000},
            {"published":True},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(self.send(self.campaign,{
                    **self.campaign_data,**variant,
                }).status_code,400)
        self.assertFalse(PointCampaignDraft.objects.exists())
        self.assert_no_effects()

    def test_permissions_isolation_and_csrf(self):
        self.client.force_login(self.analyst)
        self.assertEqual(self.send(self.reward,self.reward_data).status_code,403)
        self.assertEqual(self.send(self.campaign,self.campaign_data).status_code,403)
        self.client.force_login(self.stranger)
        self.assertEqual(self.send(self.reward,self.reward_data).status_code,404)
        self.assertEqual(self.send(self.campaign,self.campaign_data).status_code,404)
        self.client.force_login(self.owner)
        self.client.get(reverse("auth-session"))
        raw=self.client.post(self.reward,self.reward_data,format="json")
        self.assertEqual(raw.status_code,403)
        self.assert_no_effects()

    def test_draft_tenant_is_blocked_from_new_writes(self):
        self.tenant.status=Tenant.Status.DRAFT
        self.tenant.save(update_fields=["status"])
        self.assertEqual(self.send(self.reward,self.reward_data).status_code,409)
        self.assertEqual(self.send(self.campaign,self.campaign_data).status_code,409)
        self.assert_no_effects()
