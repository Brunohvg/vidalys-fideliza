"""Campanhas inteligentes: público real, grupo de comparação, oferta no Meu Clube."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent
from apps.tenants.models import Tenant, TenantMembership
from .campaign_engine import eligible_ids, offers_for, split
from .models import PointCampaignDraft, SaleRecord


@override_settings(FIDELIZA_POINTS_WRITES_ENABLED=False, FIDELIZA_LEDGER_WRITES_ENABLED=False)
class SmartCampaignTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="smart-owner")
        self.tenant = Tenant.objects.create(name="Loja Campanha", slug="loja-campanha",
                                            platform="independent", status=Tenant.Status.ACTIVE)
        self.other = Tenant.objects.create(name="Outra", slug="outra-campanha",
                                           platform="independent", status=Tenant.Status.ACTIVE)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER)
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.client.get(reverse("auth-session"))
        now = timezone.now()
        self.people = [self._member(f"Cliente {i}") for i in range(6)]
        # 0: 1 compra recente (segunda compra); 1: 2 compras; 2,3: sumiram há 100 dias; 4,5: sem compra
        self._sale(self.people[0], now - timedelta(days=5), "a")
        self._sale(self.people[1], now - timedelta(days=5), "b")
        self._sale(self.people[1], now - timedelta(days=2), "c")
        self._sale(self.people[2], now - timedelta(days=100), "d")
        self._sale(self.people[3], now - timedelta(days=100), "e")
        rejected = self._sale(self.people[4], now - timedelta(days=3), "f")
        rejected.state = SaleRecord.State.REJECTED
        rejected.save(update_fields=["state"])

    def _member(self, name, tenant=None):
        return ProgramParticipant.objects.create(
            tenant=tenant or self.tenant, display_name=name, contact_email=name.replace(" ", "") + "@example.invalid",
            external_customer_id=None, consent_at=timezone.now() - timedelta(days=200),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL, terms_version="v1",
            status=ProgramParticipant.Status.ACTIVE,
        )

    def _sale(self, participant, when, ref):
        return SaleRecord.objects.create(
            tenant=self.tenant, participant=participant, channel=SaleRecord.Channel.COUNTER,
            external_reference="VENDA-" + ref, eligible_amount_cents=5000, reported_paid_at=when,
            state=SaleRecord.State.VERIFIED_MANUAL,
        )

    def _post(self, url, data):
        self.client.get(reverse("auth-session"))
        return self.client.post(url, data, format="json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

    def test_audience_uses_real_sales_only(self):
        ids = set(eligible_ids(self.tenant.id, "second_purchase", window_days=30))
        self.assertEqual(ids, {self.people[0].id})
        lost = set(eligible_ids(self.tenant.id, "reactivation", inactive_days=60))
        self.assertEqual(lost, {self.people[2].id, self.people[3].id})
        self.assertEqual(len(eligible_ids(self.tenant.id, "multiplier")), 6)
        self.assertEqual(eligible_ids(self.tenant.id, "near_reward"), [])
        self.assertEqual(eligible_ids(self.other.id, "multiplier"), [])

    def test_comparison_group_is_stable_and_respects_limit(self):
        ids = [p.id for p in self.people]
        first = split("camp-1", ids, 50, 2)
        self.assertEqual(first, split("camp-1", ids, 50, 2))
        treated, control = first
        self.assertLessEqual(len(treated), 2)
        self.assertFalse(set(treated) & set(control))

    def test_preview_counts_audience_and_cost_without_saving(self):
        url = reverse("point-campaign-audience", kwargs={"tenant_id": self.tenant.id})
        response = self._post(url, {"goal": "reactivation", "bonus_points": 200, "max_customers": 100,
                                    "inactive_days": 60, "holdout_percent": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["audience"]["eligible"], 2)
        self.assertEqual(response.data["audience"]["reached"], 2)
        self.assertEqual(response.data["audience"]["max_cost_cents"], 400)
        self.assertFalse(PointCampaignDraft.objects.exists())

    def test_publish_requires_dates_and_shows_offer_without_crediting(self):
        today = timezone.localdate()
        created = self._post(reverse("point-campaign-drafts", kwargs={"tenant_id": self.tenant.id}), {
            "goal": "multiplier", "bonus_points": 300, "max_customers": 50, "holdout_percent": 0,
        })
        self.assertEqual(created.status_code, 201)
        cid = created.data["campaign"]["id"]
        publish = reverse("point-campaign-publish", kwargs={"tenant_id": self.tenant.id, "campaign_id": cid})
        self.assertEqual(self._post(publish, {"published": True}).status_code, 400)
        detail = reverse("point-campaign-draft-detail", kwargs={"tenant_id": self.tenant.id, "campaign_id": cid})
        self.client.get(reverse("auth-session"))
        self.client.patch(detail, {"goal": "multiplier", "bonus_points": 300, "max_customers": 50,
                                   "starts_on": today.isoformat(),
                                   "ends_on": (today + timedelta(days=7)).isoformat()},
                          format="json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        published = self._post(publish, {"published": True})
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.data["campaign"]["status"], "live")
        self.assertFalse(published.data["points_credited"])
        offers = offers_for(self.tenant.id, self.people[5].id)
        self.assertEqual(offers[0]["title"], "Pontos em dobro")
        self.assertEqual(offers[0]["multiplier"], 2)
        self.assertEqual(offers_for(self.other.id, self.people[5].id), [])
        self.assertFalse(PointEvent.objects.exists())

    def test_started_campaign_keeps_rule_for_fair_comparison(self):
        today = timezone.localdate()
        obj = PointCampaignDraft.objects.create(
            tenant=self.tenant, goal="second_purchase", bonus_points=100, max_customers=10,
            starts_on=today, ends_on=today + timedelta(days=10), published_at=timezone.now(),
            updated_by=self.owner,
        )
        detail = reverse("point-campaign-draft-detail", kwargs={"tenant_id": self.tenant.id, "campaign_id": obj.id})
        self.client.get(reverse("auth-session"))
        response = self.client.patch(detail, {"goal": "reactivation", "bonus_points": 100, "max_customers": 10},
                                     format="json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 409)

    def test_invalid_parameters_rejected(self):
        url = reverse("point-campaign-drafts", kwargs={"tenant_id": self.tenant.id})
        base = {"goal": "multiplier", "bonus_points": 100, "max_customers": 10}
        for variant in ({"multiplier": 9}, {"holdout_percent": 80}, {"starts_on": "2026-13-01"},
                        {"starts_on": "2026-11-20", "ends_on": "2026-11-10"},
                        {"starts_on": "2026-01-01", "ends_on": "2026-12-31"}, {"title": "x" * 81}):
            with self.subTest(variant=variant):
                self.assertEqual(self._post(url, {**base, **variant}).status_code, 400)
        self.assertFalse(PointCampaignDraft.objects.exists())
