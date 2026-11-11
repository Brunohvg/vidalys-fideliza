"""LGPD: HMAC oficial, entrega idempotente, isolamento e bloqueio imediato."""
import hashlib
import hmac
import json
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.participants.enrollment_models import (
    EnrollmentCustomerLink, EnrollmentEmailChallenge,
    EnrollmentInvite, EnrollmentSubmission, ProgramTerms,
)
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation, OAuthAttempt
from .privacy_models import PrivacyWebhookRequest

SECRET="private-hmac-for-synthetic-tests"


class NuvemshopPrivacyWebhookTests(TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{
            "NUVEMSHOP_CLIENT_ID":"12345",
            "NUVEMSHOP_CLIENT_SECRET":SECRET,
        })
        env.start()
        self.addCleanup(env.stop)
        self.client=Client(enforce_csrf_checks=True)
        User=get_user_model()
        self.owner=User.objects.create_user(username="privacy-merchant")
        self.tenant=Tenant.objects.create(
            name="Privacy merchant",slug="privacy-store",
            status=Tenant.Status.ACTIVE,
            platform="nuvemshop",external_store_id="91834",
        )
        TenantMembership.objects.create(tenant=self.tenant,user=self.owner,role="owner")
        self.installed=NuvemshopInstallation.objects.create(
            tenant=self.tenant,client_id="12345",store_id="91834",
            scope="read_products,read_customers",
            token_ciphertext="synthetic-encrypted-token",
        )

    def send(self,kind,payload,*,auth=True,body=None,content_type="application/json"):
        if body is None:
            body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode()
        signature=hmac.new(SECRET.encode(),body,hashlib.sha256).hexdigest()
        return self.client.post(
            reverse("nuvemshop-privacy-webhook",kwargs={"kind":kind}),
            data=body,content_type=content_type,
            **({"HTTP_X_LINKEDSTORE_HMAC_SHA256":signature} if auth else {}),
        )

    def test_requires_valid_hmac_and_raw_body_before_parsing(self):
        payload={"store_id":91834,"customer":{"id":556,"email":"secret@example.invalid"}}
        before=PrivacyWebhookRequest.objects.count()
        self.assertEqual(self.send("customer-redact",payload,auth=False).status_code,401)
        self.assertEqual(self.send("customer-redact",payload,
                                   content_type="text/plain").status_code,415)
        self.assertEqual(self.send("customer-redact",payload,body=b"{}").status_code,400)
        self.assertEqual(self.send("customer-redact",payload,
                                   body=b"x"*65537).status_code,413)
        malformed=b'{"store_id":91834'
        self.assertEqual(self.send("customer-redact",payload,body=malformed).status_code,400)
        wrong_event={**payload,"event":"app/store_redact"}
        self.assertEqual(self.send("customer-redact",wrong_event).status_code,400)
        for bad_id in (True, 0, "-3", "abc", None):
            with self.subTest(bad_id=bad_id):
                self.assertEqual(self.send("customer-redact",{
                    **payload,"customer":{"id":bad_id}
                }).status_code,400)
        self.assertEqual(PrivacyWebhookRequest.objects.count(),before)

    def test_bad_header_or_missing_secret_cannot_admit_events(self):
        payload={"store_id":91834,"customer":{"id":556}}
        body=json.dumps(payload).encode()
        with patch.dict(os.environ,{"NUVEMSHOP_CLIENT_SECRET":""}):
            self.assertEqual(self.send("customer-redact",payload).status_code,503)
        response=self.client.post(
            reverse("nuvemshop-privacy-webhook",kwargs={"kind":"customer-redact"}),
            data=body,content_type="application/json",
            HTTP_X_LINKEDSTORE_HMAC_SHA256="0"*64,
        )
        self.assertEqual(response.status_code,401)
        self.assertFalse(PrivacyWebhookRequest.objects.exists())

    def _make_submission(self,*,email="secret@example.invalid",
                         customer_id="556", linked=True):
        now=timezone.now()
        terms=ProgramTerms.objects.create(
            tenant=self.tenant,version="v1",title="Regulamento loja",
            body="Termos de privacidade para dados sintéticos. "*4,
            privacy_notice="Dados fictícios para teste somente. "*5,
            approved_at=now,active=True,
        )
        invitation=EnrollmentInvite.objects.create(
            tenant=self.tenant,terms=terms,token_digest="1"*64,
            expires_at=now+timedelta(days=1),consumed_at=now,
        )
        submission=EnrollmentSubmission.objects.create(
            tenant=self.tenant,invitation=invitation,terms=terms,
            name="Pessoa testada",email=email,
            terms_digest="2"*64,accepted_at=now,marketing_opt_in=True,
            email_verified_at=now,status=(
                EnrollmentSubmission.Status.LINKED if linked else
                EnrollmentSubmission.Status.EMAIL_VERIFIED
            ),
        )
        challenge=EnrollmentEmailChallenge.objects.create(
            submission=submission,purpose="withdraw",token_digest="3"*64,
            expires_at=now+timedelta(minutes=30),
        )
        participant=None
        if linked:
            participant=ProgramParticipant.objects.create(
                tenant=self.tenant,external_customer_id=customer_id,
                display_name="Pessoa testada",contact_email=email,
                consent_at=now,consent_channel="customer_portal",
                terms_version="v1",status=ProgramParticipant.Status.ACTIVE,
            )
            EnrollmentCustomerLink.objects.create(
                tenant=self.tenant,submission=submission,
                participant=participant,external_customer_id=customer_id,
                confirmed_by=self.owner,
            )
        return submission,challenge,participant

    def test_customer_redact_revokes_linked_contact_and_idempotently_records_review(self):
        submission,challenge,participant=self._make_submission()
        payload={
            "store_id":91834,
            "customer":{"id":556,"email":"secret@example.invalid",
                        "phone":"+55 (31) 00000-0000","identification":"documento-secreto"},
            "orders_to_redact":[123,456],
        }
        first=self.send("customer-redact",payload)
        self.assertEqual(first.status_code,202,first.content)
        self.assertEqual(first.json(),{"received":True})
        receipt=PrivacyWebhookRequest.objects.get()
        self.assertEqual(receipt.topic,"customer/redact")
        self.assertEqual(receipt.state,PrivacyWebhookRequest.State.NEEDS_REVIEW)
        self.assertEqual(receipt.customer_id,"556")
        self.assertEqual(receipt.reason_code,"pending_erasure")
        for sensitive in ("secret@example.invalid","documento-secreto","+55","orders_to_redact"):
            self.assertNotIn(sensitive,str(receipt.__dict__))
        submission.refresh_from_db()
        challenge.refresh_from_db()
        participant.refresh_from_db()
        self.assertEqual(submission.name,"")
        self.assertEqual(submission.email,"")
        self.assertFalse(submission.marketing_opt_in)
        self.assertEqual(submission.status,EnrollmentSubmission.Status.WITHDRAWN)
        self.assertEqual(participant.status,ProgramParticipant.Status.WITHDRAWN)
        self.assertEqual(participant.display_name,"")
        self.assertEqual(participant.contact_email,"")
        self.assertIsNotNone(challenge.consumed_at)

        # Webhook pode ser reenviado com atributos adicionais: mesmo evento lógico.
        other_payload={**payload,"retry_count":2,"customer":{
            **payload["customer"],"phone":"telefone-novo"
        }}
        self.assertEqual(self.send("customer-redact",other_payload).status_code,202)
        self.assertEqual(PrivacyWebhookRequest.objects.count(),1)
        self.assertEqual(ProgramParticipant.objects.count(),1)
        self.assertTrue(NuvemshopInstallation.objects.filter(tenant=self.tenant).exists())

    def test_unlinked_submission_with_matching_email_is_also_blocked(self):
        submission,challenge,member=self._make_submission(linked=False)
        self.assertIsNone(member)
        result=self.send("customer-redact",{
            "store_id":91834,"customer":{"id":556,"email":"SECRET@example.invalid"},
        })
        self.assertEqual(result.status_code,202)
        submission.refresh_from_db()
        self.assertEqual(submission.status,"withdrawn")
        self.assertEqual(submission.email,"")
        self.assertFalse(submission.marketing_opt_in)

    def test_customer_data_request_is_durable_pending_not_false_completed(self):
        payload={
            "store_id":91834,
            "customer":{"id":556,"email":"requester@example.invalid",
                        "identification":"NUNCA-PERSISTIR"},
            "orders_requested":[200], "checkouts_requested":[],
            "drafts_orders_requested":[], "data_request":{"id":777},
        }
        result=self.send("customers-data-request",payload)
        self.assertEqual(result.status_code,202)
        receipt=PrivacyWebhookRequest.objects.get()
        self.assertEqual(receipt.state,PrivacyWebhookRequest.State.PENDING)
        self.assertEqual(receipt.request_id,"777")
        self.assertEqual(receipt.reason_code,"report_not_delivered")
        self.assertNotIn("NUNCA-PERSISTIR",str(receipt.__dict__))
        self.assertEqual(self.send("customers-data-request",payload).status_code,202)
        self.assertEqual(PrivacyWebhookRequest.objects.count(),1)
        other={**payload,"data_request":{"id":778}}
        self.assertEqual(self.send("customers-data-request",other).status_code,202)
        self.assertEqual(PrivacyWebhookRequest.objects.count(),2)

    def test_store_redact_without_event_revokes_oauth_and_merchant_access(self):
        attempt=OAuthAttempt.objects.create(
            tenant=self.tenant,user=self.owner,state_digest="a"*64,
            session_digest="b"*64,client_id="12345",
            expires_at=timezone.now()+timedelta(minutes=3),
        )
        payload={"store_id":91834}
        self.assertEqual(self.send("store-redact",payload).status_code,202)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status,Tenant.Status.SUSPENDED)
        self.assertFalse(NuvemshopInstallation.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(TenantMembership.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(OAuthAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertEqual(PrivacyWebhookRequest.objects.get().state,"needs_review")
        self.assertEqual(self.send("store-redact",payload).status_code,202)
        self.assertEqual(PrivacyWebhookRequest.objects.count(),1)

    def test_unknown_store_and_wrong_app_do_not_touch_another_store(self):
        result=self.send("customer-redact",{
            "store_id":999999,"customer":{"id":556}
        })
        self.assertEqual(result.status_code,202)
        self.assertEqual(PrivacyWebhookRequest.objects.get().state,"unknown_store")
        self.assertEqual(self.tenant.status,"active")
        # Outra aplicação controla a instalação; não revogar credenciais alheias.
        self.installed.client_id="54321"
        self.installed.save(update_fields=["client_id"])
        other=self.send("store-redact",{"store_id":91834})
        self.assertEqual(other.status_code,202)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status,"active")
        self.assertTrue(NuvemshopInstallation.objects.filter(tenant=self.tenant).exists())
        self.assertTrue(TenantMembership.objects.filter(tenant=self.tenant).exists())
        self.assertEqual(PrivacyWebhookRequest.objects.count(),2)

    def test_database_failure_returns_non_2xx_for_provider_retry(self):
        with patch("apps.nuvemshop.privacy_webhooks.PrivacyWebhookRequest.objects.create",
                   side_effect=RuntimeError("synthetic-error")):
            result=self.send("customers-data-request",{
                "store_id":91834,"customer":{"id":556},"data_request":{"id":99}
            })
        self.assertEqual(result.status_code,503)
        self.assertFalse(PrivacyWebhookRequest.objects.exists())

    def test_unknown_route_is_not_accepted(self):
        self.assertEqual(self.send("invalid-topic",{"store_id":91834}).status_code,404)
