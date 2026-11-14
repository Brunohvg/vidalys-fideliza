"""PR22: smoke integrado e sintético, sem tráfego para a loja nem escrita no ledger.

CI chama endpoints DRF verdadeiros com banco temporário. A etapa de
homologação operacional (PostgreSQL externo + navegador real) é distinta.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.channels.services import issue_flow_key
from apps.customers.models import CustomerProfile, VerifiedCustomerContact
from apps.customers.services import attach_verified_contact
from apps.loyalty.models import FinancialEvidence, LoyaltyGrant, LoyaltyVoucher
from apps.participants.email_proof import digest, make_token
from apps.participants.enrollment_models import (
    EnrollmentInvite, EnrollmentSubmission, MemberAccessChallenge, ProgramTerms,
)
from apps.participants.models import ProgramParticipant
from apps.points.models import PointEntry, PointEvent, PointWallet
from apps.sales.models import SaleEventReceipt, SaleRecord
from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEntry, CashbackEvent, CashbackWallet


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=False,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=False,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset(),
    FIDELIZA_PUBLIC_SIGNUP_ENABLED=False,
)
class ConsolidationCrossAppSmokeTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.tenant = Tenant.objects.create(
            name="Loja de homologação sintética",
            slug="qa-consolidation-store",
            status=Tenant.Status.ACTIVE,
            platform="independent",
        )
        self.other = Tenant.objects.create(
            name="Outro tenant isolado",
            slug="qa-consolidation-other",
            status=Tenant.Status.ACTIVE,
            platform="independent",
        )
        self.owner = get_user_model().objects.create_user(username="qa-consolidation-owner")
        TenantMembership.objects.create(
            tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER,
        )
        _, self.flow_token = issue_flow_key(
            tenant_id=self.tenant.pk, label="Flow teste integrado", actor=self.owner,
        )
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Cliente sintético",
            contact_email="cliente-smoke@example.invalid",
            status=ProgramParticipant.Status.ACTIVE,
            consent_at=self.now,
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1",
        )
        self.profile, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            email="cliente-smoke@example.invalid", proof_method="email_otp",
        )
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            phone_e164="+5531999887766", proof_method="whatsapp_otp",
        )
        self.terms = ProgramTerms.objects.create(
            tenant=self.tenant, version="v1", title="Regulamento sintético",
            body="Não concede pontos automaticamente.", privacy_notice="Dados de testes internos.",
            approved_at=self.now,
        )
        invite = EnrollmentInvite.objects.create(
            tenant=self.tenant, terms=self.terms, token_digest="f" * 64,
            expires_at=self.now + timedelta(minutes=15), consumed_at=self.now,
        )
        self.submission = EnrollmentSubmission.objects.create(
            tenant=self.tenant, invitation=invite, terms=self.terms,
            participant=self.participant, name="Cliente sintético",
            email="cliente-smoke@example.invalid", terms_digest="d" * 64,
            accepted_at=self.now, email_verified_at=self.now,
            status=EnrollmentSubmission.Status.MEMBER,
        )
        # Compose homolog exige HTTPS. O proxy real injeta X-Forwarded-Proto;
        # fixtures exercitam a mesma condição sem relaxar SecurityMiddleware.
        self.flow = APIClient(HTTP_X_FORWARDED_PROTO="https")
        self.member = APIClient(
            enforce_csrf_checks=True,
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_REFERER="https://testserver/",
        )
        self.member.get(reverse("auth-session"))
        self.csrf = self.member.cookies["csrftoken"].value

    def ingest(self, *, reference="SMOKE-ORDER-0001", event="smoke-evt-1", status="pending",
               tenant=None, token=None):
        return self.flow.post(
            reverse("channel-order-events"),
            {
                "tenant_id": str(tenant or self.tenant.pk),
                "channel": "vidalys_flow",
                "external_order_id": reference,
                "customer_identifier": "+5531999887766",
                "total_amount": "149.90",
                "currency": "BRL",
                "status": status,
                "source_event_id": event,
            },
            format="json",
            HTTP_AUTHORIZATION="Bearer " + (token or self.flow_token),
        )

    def assert_no_credit(self):
        self.assertEqual(FinancialEvidence.objects.count(), 0)
        self.assertEqual(LoyaltyGrant.objects.count(), 0)
        self.assertEqual(LoyaltyVoucher.objects.count(), 0)
        self.assertEqual(PointWallet.objects.count(), 0)
        self.assertEqual(PointEvent.objects.count(), 0)
        self.assertEqual(PointEntry.objects.count(), 0)
        self.assertEqual(CashbackWallet.objects.count(), 0)
        self.assertEqual(CashbackEvent.objects.count(), 0)
        self.assertEqual(CashbackEntry.objects.count(), 0)

    def test_flow_paid_idempotency_phone_identity_member_portal_and_refund(self):
        # Compra informada pelo Flow; o telefone já foi comprovado via OTP
        # no cadastro sintético, não pelo webhook.
        incoming = self.ingest()
        self.assertEqual(incoming.status_code, 201, incoming.data)
        self.assertEqual(incoming.data["identity_status"], "verified_contact_match")
        self.assertFalse(incoming.data["payment_verified"])
        duplicate = self.ingest()
        self.assertEqual(duplicate.status_code, 200, duplicate.data)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(duplicate.data["sale_id"], incoming.data["sale_id"])
        self.assertEqual(duplicate.data["event_id"], incoming.data["event_id"])
        paid = self.ingest(event="smoke-evt-2", status="paid")
        self.assertEqual(paid.status_code, 200, paid.data)
        self.assertEqual(paid.data["order_status"], "paid")
        self.assertEqual(paid.data["loyalty_readiness"], "requires_independent_capture")
        self.assertFalse(paid.data["points_credited"])
        self.assertFalse(paid.data["cashback_credited"])
        sale = SaleRecord.objects.get(pk=incoming.data["sale_id"])
        self.assertEqual(sale.customer_profile_id, self.profile.pk)
        self.assertEqual(sale.order_status, SaleRecord.OrderStatus.PAID)
        self.assertEqual(sale.eligible_amount_cents, 0)
        self.assertEqual(sale.reported_total_cents, 14990)
        self.assertEqual(SaleEventReceipt.objects.filter(sale=sale).count(), 2)
        self.assertEqual(VerifiedCustomerContact.objects.filter(profile=self.profile).count(), 2)
        self.assert_no_credit()

        # A sessão de lojista NÃO basta para acessar o clube;
        # consumir link privado sintético é necessário.
        unauthorized = self.member.get(
            reverse("member-club-me", kwargs={"slug":self.tenant.slug})
        )
        self.assertEqual(unauthorized.status_code, 401)
        challenge = MemberAccessChallenge.objects.create(
            submission=self.submission, token_digest="a" * 64,
            expires_at=self.now + timedelta(minutes=15),
        )
        token = make_token(challenge.pk, "member")
        challenge.token_digest = digest(token)
        challenge.save(update_fields=["token_digest"])
        response = self.member.post(
            reverse("member-club-access-confirm", kwargs={"slug":self.tenant.slug}),
            {"token": token},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 200, response.data)
        public = self.member.get(
            reverse("member-club-public", kwargs={"slug":self.tenant.slug})
        )
        self.assertEqual(public.status_code, 200, public.data)
        member = self.member.get(
            reverse("member-club-me", kwargs={"slug":self.tenant.slug})
        )
        self.assertEqual(member.status_code, 200, member.data)
        self.assertEqual(member.data["status"], "active")
        self.assertIsNone(member.data["vip_level"])
        self.assertIsNone(member.data["points_balance"])
        self.assertIsNone(member.data["cashback_balance_cents"])
        self.assertEqual(member.data["transactions"], [])
        self.assertEqual(member.data["missions"], [])
        self.assertFalse(member.data["redemption_enabled"])
        self.assertFalse(member.data["orders_verified"])
        self.assertEqual(
            self.member.get(reverse("member-club-me", kwargs={"slug":self.other.slug})).status_code,
            401,
        )
        self.assert_no_credit()

        refund = self.ingest(event="smoke-evt-3", status="refunded")
        self.assertEqual(refund.status_code, 200, refund.data)
        sale.refresh_from_db()
        self.assertEqual(sale.order_status, SaleRecord.OrderStatus.REFUNDED)
        self.assertEqual(SaleEventReceipt.objects.filter(sale=sale).count(), 3)
        self.assert_no_credit()

    def test_unverified_phone_never_links_or_claims_another_tenant(self):
        incoming = self.flow.post(
            reverse("channel-order-events"),
            {
                "tenant_id": str(self.tenant.pk),
                "channel": "vidalys_flow",
                "external_order_id": "SMOKE-UNKNOWN-100",
                "customer_identifier": "+5531999776655",
                "total_amount": "10.50", "currency": "BRL",
                "status": "paid", "source_event_id": "smoke-unverified-1",
            },
            format="json", HTTP_AUTHORIZATION="Bearer " + self.flow_token,
        )
        self.assertEqual(incoming.status_code, 201, incoming.data)
        self.assertEqual(incoming.data["identity_status"], "provisional")
        sale = SaleRecord.objects.get(pk=incoming.data["sale_id"])
        self.assertIsNotNone(sale.customer_profile_id)
        self.assertIsNone(sale.customer_profile.participant_id)
        self.assertNotEqual(sale.customer_profile_id, self.profile.pk)
        self.assertEqual(CustomerProfile.objects.filter(tenant=self.tenant).count(), 2)
        foreign = self.ingest(tenant=self.other.pk, reference="SMOKE-FOREIGN",
                              event="smoke-foreign")
        self.assertEqual(foreign.status_code, 401)
        self.assertEqual(SaleRecord.objects.count(), 1)
        self.assert_no_credit()
