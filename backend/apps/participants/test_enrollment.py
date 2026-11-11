"""Aceite com registro próprio não cria ProgramParticipant nem saldo."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from .models import ProgramParticipant
from .enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms


@override_settings(FIDELIZA_PUBLIC_SIGNUP_ENABLED=True)
class EnrollmentPilotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="pilot-owner", password="temp-only")
        self.admin = User.objects.create_user(username="pilot-admin")
        self.analyst = User.objects.create_user(username="pilot-analyst")
        self.stranger = User.objects.create_user(username="pilot-stranger")
        self.tenant = Tenant.objects.create(name="Loja piloto", slug="pilot-signup")
        self.other = Tenant.objects.create(name="Outra loja", slug="other-pilot-signup")
        for user, tenant, role in [
            (self.owner, self.tenant, "owner"), (self.admin, self.tenant, "admin"),
            (self.analyst, self.tenant, "analyst"),
            (self.stranger, self.other, "owner"),
        ]:
            TenantMembership.objects.create(user=user, tenant=tenant, role=role)
        self.client = APIClient()
        self.terms_data = {
            "version": "piloto-v1", "title": "Regulamento de adesão",
            "body": "Este programa de teste registra um aceite voluntário e não distribui "
                    "descontos, vantagens, pontos ou cashback durante a homologação. "
                    "A participação dependerá da confirmação da identidade pela loja.",
        }

    def url(self, name, tenant=None):
        return reverse(name, kwargs={"tenant_id": tenant or self.tenant.pk})

    def approve(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(self.url("tenant-program-terms"), self.terms_data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def invite(self):
        self.approve()
        result = self.client.post(self.url("tenant-enrollment-invitations"), {}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result["Cache-Control"], "private, no-store")
        return result.data["token"]

    def accept(self, token, **kwargs):
        client = APIClient()
        return client.post(reverse("public-enrollment-accept"), {
            "token": token, "name": "Pessoa convidada", "email": "pessoa@example.invalid",
            "accepted_terms": True, "marketing_opt_in": False, **kwargs,
        }, format="json")

    def test_auth_roles_and_tenant_isolation(self):
        self.assertIn(self.client.get(self.url("tenant-program-terms")).status_code, (401, 403))
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.post(self.url("tenant-program-terms"),
            self.terms_data, format="json").status_code, 404)
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get(self.url("tenant-program-terms")).status_code, 200)
        self.assertEqual(self.client.post(self.url("tenant-program-terms"),
            self.terms_data, format="json").status_code, 403)
        self.assertEqual(self.client.post(self.url("tenant-enrollment-invitations"),
            {}, format="json").status_code, 403)
        self.assertEqual(self.client.get(self.url("tenant-enrollment-submissions")).status_code, 403)

    def test_terms_require_approval_and_are_versioned(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(self.url("tenant-enrollment-invitations"),
            {}, format="json").status_code, 409)
        self.assertEqual(self.client.post(self.url("tenant-program-terms"),
            {"version": "x", "title": "a", "body": "b"}, format="json").status_code, 400)
        self.approve()
        self.assertEqual(self.client.post(self.url("tenant-program-terms"),
            self.terms_data, format="json").status_code, 409)
        version2 = {**self.terms_data, "version": "piloto-v2"}
        response = self.client.post(self.url("tenant-program-terms"), version2, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ProgramTerms.objects.filter(active=True, tenant=self.tenant).count(), 1)
        self.assertEqual(ProgramTerms.objects.count(), 2)

    def test_invite_single_use_and_no_real_membership(self):
        token = self.invite()
        invitation = EnrollmentInvite.objects.get()
        self.assertEqual(invitation.token_digest.__len__(), 64)
        self.assertNotIn(token, invitation.token_digest)
        preview = APIClient().post(reverse("public-enrollment-preview"), {"token": token}, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["store_name"], self.tenant.name)
        self.assertFalse(preview.data["identity_verified"])
        self.assertEqual(preview.data["terms"]["body"], self.terms_data["body"])
        receipt = self.accept(token, marketing_opt_in=True)
        self.assertEqual(receipt.status_code, 201, receipt.data)
        self.assertFalse(receipt.data["participant_created"])
        self.assertFalse(receipt.data["cashback_enabled"])
        self.assertEqual(ProgramParticipant.objects.count(), 0)
        self.assertEqual(EnrollmentSubmission.objects.count(), 1)
        self.assertEqual(EnrollmentSubmission.objects.get().marketing_opt_in, True)
        self.assertEqual(EnrollmentSubmission.objects.get().terms.version, "piloto-v1")
        again = self.accept(token)
        self.assertEqual(again.status_code, 410)
        self.assertEqual(EnrollmentSubmission.objects.count(), 1)

    def test_no_consent_no_submission(self):
        token = self.invite()
        bad_cases = [
            {"accepted_terms": False}, {"accepted_terms": "true"},
            {"marketing_opt_in": "yes"}, {"email": "invalid"},
            {"name": "x"}, {"name": "\nunsafe"},
        ]
        for changes in bad_cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.accept(token, **changes).status_code, 400)
        self.assertEqual(EnrollmentSubmission.objects.count(), 0)
        self.assertIsNone(EnrollmentInvite.objects.get().consumed_at)

    def test_old_terms_cancel_pending_invites(self):
        token = self.invite()
        next_terms = {**self.terms_data, "version": "piloto-v2"}
        self.client.post(self.url("tenant-program-terms"), next_terms, format="json")
        expired = APIClient().post(reverse("public-enrollment-preview"), {"token": token}, format="json")
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(self.accept(token).status_code, 410)
        self.assertEqual(EnrollmentSubmission.objects.count(), 0)

    def test_pending_list_contains_only_authorized_tenant_records(self):
        token = self.invite()
        self.accept(token)
        self.client.force_authenticate(self.owner)
        listed = self.client.get(self.url("tenant-enrollment-submissions"))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["total"], 1)
        self.assertEqual(listed.data["items"][0]["status"], "pending_verification")
        self.client.force_authenticate(self.stranger)
        hidden = self.client.get(self.url("tenant-enrollment-submissions", self.other.pk))
        self.assertEqual(hidden.data["total"], 0)

    def test_strict_payload_no_unverified_identity(self):
        self.client.force_authenticate(self.owner)
        self.approve()
        self.assertEqual(self.client.post(self.url("tenant-enrollment-invitations"),
            {"external_customer_id": "123"}, format="json").status_code, 400)
        self.assertEqual(EnrollmentInvite.objects.count(), 0)
        self.assertEqual(ProgramParticipant.objects.count(), 0)

    def test_public_accept_requires_csrf_even_when_not_authenticated(self):
        token = self.invite()
        public = APIClient(enforce_csrf_checks=True)
        body = {
            "token": token, "name": "Pessoa convidada", "email": "pessoa@example.invalid",
            "accepted_terms": True, "marketing_opt_in": False,
        }
        missing = public.post(reverse("public-enrollment-accept"), body, format="json")
        self.assertEqual(missing.status_code, 403)
        token_response = public.get(reverse("auth-session"))
        self.assertEqual(token_response.status_code, 200)
        csrf = public.cookies.get("csrftoken")
        self.assertIsNotNone(csrf)
        response = public.post(reverse("public-enrollment-accept"), body,
                               format="json", HTTP_X_CSRFTOKEN=csrf.value)
        self.assertEqual(response.status_code, 201, response.content)

    def test_post_cannot_approve_or_credit(self):
        token = self.invite()
        public = APIClient()
        result = public.post(reverse("public-enrollment-accept"), {
            "token": token, "name": "Pessoa convidada", "email": "pessoa@example.invalid",
            "accepted_terms": True, "marketing_opt_in": False,
            "status": "active", "cashback_balance_cents": 50000,
        }, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertEqual(EnrollmentSubmission.objects.count(), 0)
