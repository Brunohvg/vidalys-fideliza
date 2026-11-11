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
from apps.wallets.models import CashbackWallet, CashbackEvent, CashbackEntry

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
        self.assertTrue(participant.external_customer_id.startswith("anon:"))
        self.assertNotEqual(participant.external_customer_id,"556")
        link=EnrollmentCustomerLink.objects.get(participant=participant)
        self.assertEqual(link.external_customer_id,participant.external_customer_id)
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

    def test_unknown_store_is_reconciled_safely_if_provider_retries(self):
        payload={"store_id":234567,"customer":{"id":555,"email":"new@example.invalid"}}
        self.assertEqual(self.send("customer-redact",payload).status_code,202)
        request=PrivacyWebhookRequest.objects.get(store_id="234567")
        self.assertEqual(request.state,"unknown_store")
        new_store=Tenant.objects.create(
            name="Loja mapeada depois",slug="mapped-late",
            status="active",external_store_id="234567",platform="nuvemshop",
        )
        NuvemshopInstallation.objects.create(
            tenant=new_store,client_id="12345",store_id="234567",
            scope="read_products",token_ciphertext="synthetic-token",
        )
        member=ProgramParticipant.objects.create(
            tenant=new_store,external_customer_id="555",
            display_name="Contato antigo",contact_email="new@example.invalid",
            consent_at=timezone.now(),consent_channel="customer_portal",
            terms_version="v1",status="active",
        )
        self.assertEqual(self.send("customer-redact",payload).status_code,202)
        request.refresh_from_db()
        member.refresh_from_db()
        self.assertEqual(request.state,"needs_review")
        self.assertEqual(request.tenant_id,new_store.id)
        self.assertEqual(PrivacyWebhookRequest.objects.count(),1)
        self.assertEqual(member.status,"withdrawn")
        self.assertEqual(member.contact_email,"")

    def test_database_failure_returns_non_2xx_for_provider_retry(self):
        with patch("apps.nuvemshop.privacy_webhooks.PrivacyWebhookRequest.objects.create",
                   side_effect=RuntimeError("synthetic-error")):
            result=self.send("customers-data-request",{
                "store_id":91834,"customer":{"id":556},"data_request":{"id":99}
            })
        self.assertEqual(result.status_code,503)
        self.assertFalse(PrivacyWebhookRequest.objects.exists())

    def test_merchant_summary_is_isolated_and_never_exposes_personal_data(self):
        self.assertEqual(self.send("customers-data-request",{
            "store_id":91834,
            "customer":{"id":556,"email":"private@example.invalid",
                        "phone":"+55 31 90000-0000"},
            "data_request":{"id":801},
        }).status_code,202)
        path=reverse("tenant-privacy-requests",kwargs={"tenant_id":self.tenant.id})
        self.assertIn(self.client.get(path).status_code,(302,401,403))
        self.client.force_login(self.owner)
        response=self.client.get(path)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()["pending_total"],1)
        self.assertEqual(response.json()["access_requests"],1)
        self.assertEqual(response.json()["deletion_requests"],0)
        self.assertEqual(response["Cache-Control"],"private, no-store")
        for secret in ("556","801","private@example.invalid","+55","91834"):
            self.assertNotIn(secret,response.content.decode())
        # Nenhum vazamento cruzado, inclusive para membro da loja errada.
        foreign=Tenant.objects.create(
            name="Outra loja",slug="privacy-foreign",platform="nuvemshop",
            external_store_id="999999",
        )
        outsider=get_user_model().objects.create_user(username="privacy-outsider")
        TenantMembership.objects.create(tenant=foreign,user=outsider,role="owner")
        self.assertEqual(self.client.get(reverse("tenant-privacy-requests",kwargs={
            "tenant_id":foreign.id
        })).status_code,404)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(path).status_code,404)
        analyst=get_user_model().objects.create_user(username="privacy-analyst")
        TenantMembership.objects.create(tenant=self.tenant,user=analyst,role="analyst")
        self.client.force_login(analyst)
        self.assertEqual(self.client.get(path).status_code,403)

    def _privacy_report_request(self,*,email="secret@example.invalid",request_id=995):
        customer={"id":556}
        if email is not None:
            customer["email"]=email
        self.assertEqual(self.send("customers-data-request",{
            "store_id":91834,"customer":customer,
            "data_request":{"id":request_id},
            "orders_requested":[18,29],
        }).status_code,202)
        return PrivacyWebhookRequest.objects.get(request_id=str(request_id))

    def _report_auth(self,user=None):
        self.client.force_login(user or self.owner)
        self.client.get("/api/v1/auth/session/",secure=True)
        return {"secure":True,
                "HTTP_X_CSRFTOKEN":self.client.cookies["csrftoken"].value,
                "HTTP_ORIGIN":"https://testserver"}

    def _post_report(self,receipt,action="report",data=None,**headers):
        path=reverse("tenant-privacy-report" if action=="report"
                     else "tenant-privacy-report-confirm",
                     kwargs={"tenant_id":self.tenant.id,"request_id":receipt.id})
        return self.client.post(path,
                data=json.dumps(data if data is not None else {}),
                content_type="application/json",**headers)

    def test_report_exports_only_matching_customer_app_data(self):
        submission,challenge,participant=self._make_submission()
        wallet=CashbackWallet.objects.create(tenant=self.tenant,participant=participant)
        event=CashbackEvent.objects.create(
            wallet=wallet,kind="accrual",amount_cents=90,
            rule_version="test-rule",source_order_id="order-123",
            idempotency_key="test-report-event",
        )
        CashbackEntry.objects.create(
            event=event,bucket="pending",delta_cents=90,
        )
        receipt=self._privacy_report_request()
        self.assertEqual(len(receipt.customer_email_digest),64)
        foreign=Tenant.objects.create(name="Loja estranha",slug="private-other",
                                     external_store_id="765432",status="active")
        ProgramParticipant.objects.create(
            tenant=foreign,external_customer_id="556",
            display_name="SENSITIVE OTHER TENANT",contact_email="other@example.invalid",
            consent_at=timezone.now(),consent_channel="customer_portal",
            terms_version="old",
        )
        headers=self._report_auth()
        report=self._post_report(receipt,**headers)
        self.assertEqual(report.status_code,200,report.content)
        self.assertIn("attachment;",report["Content-Disposition"])
        self.assertEqual(report["Cache-Control"],"private, no-store, max-age=0")
        self.assertEqual(report["X-Fideliza-Report-Complete"],"true")
        data=json.loads(report.content)
        self.assertEqual(data["solicitacao"],"995")
        self.assertEqual(len(data["participacoes"]),1)
        self.assertEqual(len(data["aceites"]),1)
        self.assertEqual(data["aceites"][0]["email"],"secret@example.invalid")
        self.assertEqual(data["movimentos_financeiros_internos"][0]["valor_centavos"],90)
        for secret in ("SENSITIVE OTHER TENANT","other@example.invalid",
                       "synthetic-encrypted-token","token_digest",
                       "idempotency_key","9876","orders_requested"):
            self.assertNotIn(secret,report.content.decode())
        digest=hashlib.sha256(report.content).hexdigest()
        self.assertEqual(report["X-Fideliza-Report-Digest"],digest)
        receipt.refresh_from_db()
        self.assertEqual(receipt.state,"pending")
        self.assertEqual(receipt.report_digest,digest)
        self.assertEqual(receipt.report_accessed_by,self.owner)
        self.assertIsNotNone(receipt.report_accessed_at)

        self.assertEqual(
            self._post_report(receipt,action="confirm",
                              data={"confirm":True,"digest":digest},
                              **headers).status_code,200)
        receipt.refresh_from_db()
        self.assertEqual(receipt.state,"completed")
        self.assertEqual(receipt.delivery_confirmed_by,self.owner)
        self.assertIsNotNone(receipt.processed_at)
        self.assertEqual(receipt.reason_code,"merchant_confirmed_download")
        self.assertEqual(self._post_report(receipt,**headers).status_code,409)
        self.assertEqual(self._post_report(receipt,action="confirm",
                        data={"confirm":True,"digest":digest},**headers).status_code,409)

    def test_unlinked_consent_included_via_hmac_email_only(self):
        submission,_,_=self._make_submission(linked=False)
        receipt=self._privacy_report_request(email="SECRET@example.invalid")
        report=self._post_report(receipt,**self._report_auth())
        self.assertEqual(report.status_code,200)
        data=json.loads(report.content)
        self.assertEqual(data["participacoes"],[])
        self.assertEqual(len(data["aceites"]),1)
        self.assertEqual(data["aceites"][0]["id"],str(submission.id))
        self.assertEqual(report["X-Fideliza-Report-Complete"],"true")

    def test_report_without_customer_email_requires_manual_review(self):
        self._make_submission(linked=False)
        receipt=self._privacy_report_request(email=None)
        headers=self._report_auth()
        report=self._post_report(receipt,**headers)
        self.assertEqual(report.status_code,200)
        self.assertEqual(report["X-Fideliza-Report-Complete"],"false")
        self.assertFalse(json.loads(report.content)["cobertura"]["aceites_sem_vinculo_identificaveis"])
        result=self._post_report(
            receipt,action="confirm",
            data={"confirm":True,"digest":report["X-Fideliza-Report-Digest"]},
            **headers,
        )
        self.assertEqual(result.status_code,409)
        receipt.refresh_from_db()
        self.assertEqual(receipt.state,"pending")

    def test_changed_report_and_wrong_checksum_cannot_be_confirmed(self):
        submission,_,_=self._make_submission()
        receipt=self._privacy_report_request()
        headers=self._report_auth()
        report=self._post_report(receipt,**headers)
        self.assertEqual(self._post_report(receipt,action="confirm",
                         data={"confirm":True,"digest":"0"*64},**headers).status_code,409)
        submission.name="Nome atualizado após download"
        submission.save(update_fields=["name"])
        result=self._post_report(receipt,action="confirm",
            data={"confirm":True,"digest":report["X-Fideliza-Report-Digest"]},**headers)
        self.assertEqual(result.status_code,409)
        receipt.refresh_from_db()
        self.assertEqual(receipt.state,"pending")
        newer=self._post_report(receipt,**headers)
        self.assertNotEqual(newer["X-Fideliza-Report-Digest"],
                            report["X-Fideliza-Report-Digest"])
        self.assertEqual(self._post_report(
            receipt,action="confirm",
            data={"confirm":True,"digest":newer["X-Fideliza-Report-Digest"]},
            **headers).status_code,200)

    def test_report_requires_csrf_and_owner_in_correct_store(self):
        receipt=self._privacy_report_request()
        path=reverse("tenant-privacy-report",kwargs={
            "tenant_id":self.tenant.id,"request_id":receipt.id
        })
        self.assertIn(self._post_report(receipt).status_code,(401,403))
        self.client.force_login(self.owner)
        self.assertEqual(self._post_report(receipt).status_code,403)
        headers=self._report_auth()
        self.assertEqual(self.client.get(path,secure=True).status_code,405)
        self.assertEqual(self._post_report(receipt,
                        data={"email":"someone@example.invalid"},**headers).status_code,400)
        outsider=get_user_model().objects.create_user(username="privacy-report-outsider")
        other=Tenant.objects.create(name="Foreign",slug="privacy-report-other")
        TenantMembership.objects.create(user=outsider,tenant=other,role="owner")
        self._report_auth(outsider)
        self.assertEqual(self._post_report(receipt,**self._report_auth(outsider)).status_code,404)
        analyst=get_user_model().objects.create_user(username="privacy-report-analyst")
        TenantMembership.objects.create(user=analyst,tenant=self.tenant,role="analyst")
        self.assertEqual(self._post_report(receipt,**self._report_auth(analyst)).status_code,403)
        receipt.refresh_from_db()
        self.assertEqual(receipt.report_digest,"")

    def test_unknown_route_is_not_accepted(self):
        self.assertEqual(self.send("invalid-topic",{"store_id":91834}).status_code,404)
