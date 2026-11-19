"""Perfil do cliente, entrada por código, sessão lembrada e app instalável."""
from datetime import datetime, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_proof import make_code
from .enrollment_models import EnrollmentSubmission, MemberAccessChallenge
from .models import ProgramParticipant
from . import test_member_portal as access_tests


@override_settings(FIDELIZA_EMAIL_DELIVERY_ENABLED=True, FIDELIZA_PUBLIC_BASE_URL="https://staging.invalid",
                   FIDELIZA_LEDGER_WRITES_ENABLED=False)
class MemberProfileTests(TestCase):
    # Mesmo cenário dos testes de acesso, sem repetir aqueles testes.
    setUp = access_tests.MemberClubAccessTests.setUp
    call = access_tests.MemberClubAccessTests.call
    request_link = access_tests.MemberClubAccessTests.request_link

    def enter_with_code(self, remember=False):
        self.request_link()
        code = make_code(MemberAccessChallenge.objects.get().id)
        return self.call("member-club-access-code", {
            "email": "MEMBRO@example.invalid", "code": code[:3] + " " + code[3:], "remember": remember,
        })

    def patch_profile(self, data):
        return self.api.patch(reverse("member-club-profile", kwargs={"slug": self.tenant.slug}),
                              data, format="json", HTTP_X_CSRFTOKEN=self.csrf)

    def test_code_logs_in_once_and_remember_extends_session(self):
        response = self.enter_with_code(remember=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["remembered"])
        me = self.api.get(reverse("member-club-me", kwargs={"slug": self.tenant.slug}))
        self.assertEqual(me.status_code, 200)
        expires = datetime.fromisoformat(me.data["session_expires_at"])
        self.assertGreater(expires, timezone.now() + timedelta(days=170))
        self.assertEqual(me.data["email"], "membro@example.invalid")
        # Código já usado não vale de novo.
        code = make_code(MemberAccessChallenge.objects.get().id)
        again = self.call("member-club-access-code", {"email": "membro@example.invalid", "code": code})
        self.assertEqual(again.status_code, 410)

    def test_wrong_code_locks_after_five_attempts(self):
        self.request_link()
        challenge = MemberAccessChallenge.objects.get()
        right = make_code(challenge.id)
        wrong = "000000" if right != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.call("member-club-access-code",
                                       {"email": "membro@example.invalid", "code": wrong}).status_code, 410)
        self.assertEqual(self.call("member-club-access-code",
                                   {"email": "membro@example.invalid", "code": right}).status_code, 410)
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.consumed_at)

    def test_code_from_other_store_does_not_work(self):
        self.request_link()
        code = make_code(MemberAccessChallenge.objects.get().id)
        response = self.call("member-club-access-code", {"email": "membro@example.invalid", "code": code},
                             slug=self.other.slug)
        self.assertEqual(response.status_code, 410)

    def test_member_updates_profile_birthday_phone_and_preferences(self):
        self.enter_with_code()
        participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Pessoa Teste", contact_email=self.submission.email,
            external_customer_id=None, consent_at=self.submission.accepted_at,
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version=self.terms.version, status=ProgramParticipant.Status.ACTIVE,
        )
        self.submission.participant = participant
        self.submission.status = EnrollmentSubmission.Status.MEMBER
        self.submission.save(update_fields=["participant", "status"])
        response = self.patch_profile({"name": "Pessoa Renomeada", "phone": "(31) 98888-7777",
                                       "birth_day": 29, "birth_month": 2, "marketing_opt_in": True})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["profile"]["phone_last4"], "7777")
        self.submission.refresh_from_db(); participant.refresh_from_db()
        self.assertEqual((self.submission.birth_day, self.submission.birth_month), (29, 2))
        self.assertTrue(self.submission.marketing_opt_in)
        self.assertEqual(participant.display_name, "Pessoa Renomeada")
        self.assertEqual(participant.phone_last4, "7777")
        self.assertNotIn("988887777", str(response.data))

    def test_profile_rejects_invalid_data_and_requires_login(self):
        self.assertEqual(self.patch_profile({"name": "Nome"}).status_code, 401)
        self.enter_with_code()
        for data in ({"birth_day": 31, "birth_month": 2}, {"birth_day": 10}, {"name": "ab"},
                     {"phone": "123"}, {"marketing_opt_in": "sim"}, {"email": "x@y.z"}, {}):
            with self.subTest(data=data):
                self.assertEqual(self.patch_profile(data).status_code, 400)

    def test_export_returns_own_data_as_file(self):
        self.enter_with_code()
        response = self.api.get(reverse("member-club-export", kwargs={"slug": self.tenant.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("membro@example.invalid", response.content.decode())

    def test_manifest_and_icon_use_store_identity(self):
        manifest = self.api.get(reverse("member-club-manifest", kwargs={"slug": self.tenant.slug}))
        self.assertEqual(manifest.status_code, 200)
        data = manifest.json()
        self.assertEqual(data["start_url"], "/clube/clube-qa?origem=app")
        self.assertEqual(data["display"], "standalone")
        self.assertNotIn("membro@example.invalid", manifest.content.decode())
        icon = self.api.get(reverse("member-club-icon", kwargs={"slug": self.tenant.slug}))
        self.assertEqual(icon.status_code, 200)
        self.assertIn("<svg", icon.content.decode())
        self.assertIn(">LQ<", icon.content.decode())
