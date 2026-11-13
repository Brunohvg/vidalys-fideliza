"""Contrato mínimo do canal manual: isolamento, idempotência e zero crédito."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEvent, CashbackWallet
from .models import PointRuleDraft, SaleRecord
from .quote import preview_points


@override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=False)
class ManualSalesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="cashier-owner")
        self.reviewer = User.objects.create_user(username="cashier-reviewer")
        self.analyst = User.objects.create_user(username="cashier-analyst")
        self.stranger = User.objects.create_user(username="cashier-stranger")
        self.tenant = Tenant.objects.create(
            name="Loja Balcão QA", slug="cashier-qa", platform="independent",
            status=Tenant.Status.ACTIVE,
        )
        self.other = Tenant.objects.create(
            name="Outra Loja QA", slug="cashier-other", platform="independent",
            status=Tenant.Status.ACTIVE,
        )
        for user, role in (
            (self.owner, TenantMembership.Role.OWNER),
            (self.reviewer, TenantMembership.Role.ADMIN),
            (self.analyst, TenantMembership.Role.ANALYST),
        ):
            TenantMembership.objects.create(
                user=user, tenant=self.tenant, role=role,
            )
        now = timezone.now() - timedelta(minutes=2)
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Participante QA",
            contact_email="member@example.invalid",
            external_customer_id=None, consent_at=now,
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )
        self.other_member = ProgramParticipant.objects.create(
            tenant=self.other, display_name="Outro membro",
            contact_email="other@example.invalid",
            external_customer_id=None, consent_at=now,
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.client.get(reverse("auth-session"))
        self.paid = timezone.now().isoformat()
        self.body = {
            "reference": "VENDA-00042", "eligible_amount_cents": 10000,
            "participant_id": str(self.participant.id),
            "reported_paid_at": self.paid,
            "evidence_reference": "CUPOM-00042",
        }

    def csrf_post(self, name, payload, tenant=None, sale_id=None):
        kwargs = {"tenant_id": (tenant or self.tenant).id}
        if sale_id:
            kwargs["sale_id"] = sale_id
        self.client.get(reverse("auth-session"))
        return self.client.post(
            reverse(name, kwargs=kwargs), payload, format="json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

    def create(self, payload=None):
        return self.csrf_post("manual-sales", self.body if payload is None else payload)

    def test_manual_sale_is_review_only_and_idempotent(self):
        first = self.create()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertFalse(first.data["already_recorded"])
        self.assertEqual(first.data["sale"]["state"], "awaiting_review")
        second = self.create()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertTrue(second.data["already_recorded"])
        self.assertEqual(SaleRecord.objects.count(), 1)
        self.assertFalse(CashbackEvent.objects.exists())
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertEqual(
            self.client.get(reverse("manual-sales",kwargs={"tenant_id":self.tenant.id})).data["items"][0]["reference"],
            "VENDA-00042",
        )
        altered = {**self.body,"eligible_amount_cents":12000}
        self.assertEqual(self.create(altered).status_code, 409)
        self.assertEqual(SaleRecord.objects.count(), 1)

    def test_second_operator_required_and_no_payout_after_review(self):
        created=self.create()
        sale_id=created.data["sale"]["id"]
        review={"decision":"approve","note":"Cupom e caixa conferidos pela equipe."}
        self.assertEqual(self.csrf_post("manual-sale-review",review,sale_id=sale_id).status_code,409)
        self.client.force_login(self.reviewer)
        response=self.csrf_post("manual-sale-review",review,sale_id=sale_id)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["sale"]["state"],SaleRecord.State.VERIFIED_MANUAL)
        self.assertFalse(response.data["independent_payment_proof"])
        self.assertFalse(response.data["points_credited"])
        self.assertEqual(
            self.csrf_post("manual-sale-review",review,sale_id=sale_id).status_code,409,
        )
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    def test_non_participant_sale_is_opportunity_not_points(self):
        payload={**self.body,"participant_id":None}
        response=self.create(payload)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data["sale"]["state"],SaleRecord.State.AWAITING_MEMBER)
        self.client.force_login(self.reviewer)
        check=self.csrf_post("manual-sale-review",{
            "decision":"approve","note":"Conferência de comprovante de balcão."},
            sale_id=response.data["sale"]["id"])
        self.assertEqual(check.status_code,409)
        self.assertFalse(CashbackWallet.objects.exists())

    def test_cross_tenant_participant_is_rejected(self):
        foreign = {**self.body,"participant_id":str(self.other_member.id)}
        self.assertEqual(self.create(foreign).status_code,409)
        self.assertFalse(SaleRecord.objects.exists())

    def test_pre_enrollment_sale_is_rejected(self):
        payload={**self.body,"reported_paid_at":(
            self.participant.consent_at-timedelta(seconds=1)).isoformat()}
        self.assertEqual(self.create(payload).status_code,409)
        self.assertFalse(SaleRecord.objects.exists())

    def test_invalid_amount_timestamp_and_uuid_are_rejected(self):
        for field,value in [
            ("eligible_amount_cents",True),("eligible_amount_cents",-1),
            ("eligible_amount_cents",1_000_000_000),
            ("participant_id","not-a-uuid"),
            ("reported_paid_at","not a date"),
            ("reported_paid_at",(timezone.now()+timedelta(days=1)).isoformat()),
            ("evidence_reference","card number 1234 5678"),
        ]:
            with self.subTest(field=field,value=value):
                self.assertEqual(self.create({**self.body,field:value}).status_code,400)
        self.assertFalse(SaleRecord.objects.exists())

    def test_permissions_and_cross_tenant_access(self):
        self.client.force_login(self.analyst)
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.client.get(reverse("manual-sales",kwargs={
            "tenant_id":self.tenant.id,
        })).status_code,403)
        self.client.force_login(self.stranger)
        self.assertEqual(self.create().status_code,404)
        self.assertFalse(SaleRecord.objects.exists())

    def test_csrf_is_required_and_suspended_tenant_cannot_write(self):
        self.client.get(reverse("auth-session"))
        response=self.client.post(
            reverse("manual-sales",kwargs={"tenant_id":self.tenant.id}),
            self.body,format="json",
        )
        self.assertEqual(response.status_code,403)
        self.tenant.status=Tenant.Status.SUSPENDED
        self.tenant.save(update_fields=["status"])
        self.assertEqual(self.create().status_code,409)


@override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=False)
class PointRuleDraftTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user(username="points-owner")
        self.analyst=User.objects.create_user(username="points-analyst")
        self.tenant=Tenant.objects.create(
            name="Loja Simulação",slug="points-sandbox",
            status=Tenant.Status.ACTIVE,platform="independent",
        )
        for user,role in [(self.owner,TenantMembership.Role.OWNER),
                          (self.analyst,TenantMembership.Role.ANALYST)]:
            TenantMembership.objects.create(user=user,tenant=self.tenant,role=role)
        self.api=APIClient(enforce_csrf_checks=True)
        self.api.force_login(self.owner)
        self.api.get(reverse("auth-session"))
        self.url=reverse("point-rule-draft",kwargs={"tenant_id":self.tenant.id})
        self.body={"points":1,"per_cents":100,"hold_days":7,"validity_days":180}

    def post(self,payload):
        self.api.get(reverse("auth-session"))
        return self.api.post(self.url,payload,format="json",
            HTTP_X_CSRFTOKEN=self.api.cookies["csrftoken"].value)

    def test_versioned_draft_preview_not_published(self):
        self.assertIsNone(self.api.get(self.url).data["rule"])
        first=self.post(self.body)
        self.assertEqual(first.status_code,200,first.data)
        self.assertEqual(first.data["example_for_100_reais"],100)
        self.assertEqual(first.data["version"],1)
        self.assertFalse(first.data["activation_available"])
        self.assertFalse(first.data["points_credited"])
        self.assertEqual(self.post(self.body).data["version"],1)
        changed=self.post({**self.body,"points":2})
        self.assertEqual(changed.data["version"],2)
        self.assertEqual(changed.data["example_for_100_reais"],200)
        self.assertEqual(PointRuleDraft.objects.count(),1)
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    def test_invalid_rule_fails_closed_and_analyst_cannot_modify(self):
        for value in [-1,0,True,1.5,100001]:
            with self.subTest(value=value):
                self.assertEqual(self.post({**self.body,"points":value}).status_code,400)
        self.assertEqual(self.post({**self.body,"activation_enabled":True}).status_code,400)
        self.api.force_login(self.analyst)
        self.assertEqual(self.post(self.body).status_code,403)
        self.assertFalse(PointRuleDraft.objects.exists())

    def test_quote_is_integer_and_amount_below_base_rounds_down(self):
        self.assertEqual(preview_points(eligible_amount_cents=199,points=1,per_cents=100),1)
        self.assertEqual(preview_points(eligible_amount_cents=99,points=1,per_cents=100),0)
        with self.assertRaises(ValueError):
            preview_points(eligible_amount_cents=True,points=1,per_cents=100)
