"""Jornada integrada com dados sintéticos, sem SMTP, Nuvemshop ou cashback real.

Cobre a fronteira entre as APIs públicas, a prova de e-mail, a consulta
autorizada do cadastro e o painel privado do lojista. O que depende de
provedores reais permanece fora de escopo.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.security import OAuthConfig
from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEvent, CashbackWallet

from .email_proof import make_token
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission, EnrollmentCustomerLink
from .models import ProgramParticipant


@override_settings(
    FIDELIZA_PUBLIC_SIGNUP_ENABLED=True,
    FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    FIDELIZA_PUBLIC_BASE_URL="https://fideliza-homolog.optarys.com.br",
    FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True,
    FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class CompleteHomologJourneyTests(TestCase):
    def setUp(self):
        cache.clear()
        User=get_user_model()
        self.owner=User.objects.create_user(username="journey-owner")
        self.other=User.objects.create_user(username="journey-foreign")
        self.tenant=Tenant.objects.create(
            name="Loja sintética",slug="journey-full",status=Tenant.Status.ACTIVE,
            platform="nuvemshop",external_store_id="8731",
        )
        self.foreign=Tenant.objects.create(
            name="Loja externa",slug="journey-other",status=Tenant.Status.ACTIVE,
            platform="nuvemshop",external_store_id="9981",
        )
        TenantMembership.objects.create(
            tenant=self.tenant,user=self.owner,role=TenantMembership.Role.OWNER
        )
        TenantMembership.objects.create(
            tenant=self.foreign,user=self.other,role=TenantMembership.Role.OWNER
        )
        self.owner_client=APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.public=APIClient(enforce_csrf_checks=True)
        self.public.get(reverse("auth-session"))
        self.csrf=self.public.cookies["csrftoken"].value
        self.customer_cfg=OAuthConfig(
            client_id="12345",client_secret="synthetic-secret",
            callback_url="https://staging.invalid/api/v1/oauth/nuvemshop/callback/",
            user_agent="Vidalys Fideliza (qa@example.invalid)",
            token_keys="dummy-test-keys",
        )
        NuvemshopInstallation.objects.create(
            tenant=self.tenant,store_id="8731",client_id="12345",
            scope="read_products,read_customers",
            token_ciphertext="synthetic-ciphertext",
        )

    def tenant_url(self,name,**kwargs):
        return reverse(name,kwargs={"tenant_id":self.tenant.pk,**kwargs})

    def public_post(self,name,data,**kwargs):
        return self.public.post(reverse(name,kwargs=kwargs),data,format="json",
                                HTTP_X_CSRFTOKEN=self.csrf)

    def test_consent_email_approval_wallet_withdrawal_and_isolation(self):
        # 1. O responsável aprova o regulamento, sem publicar cashback.
        terms=self.owner_client.post(self.tenant_url("tenant-program-terms"),{
            "version":"journey-v1",
            "title":"Regulamento de homologação",
            "body":"Este programa fictício registra somente consentimento e adesão. "
                   "Nenhum crédito, pagamento, desconto ou recompensa será concedido. "*2,
            "privacy_notice":"A loja responsável recebe um pedido de adesão e "
                "confirma o cadastro do consumidor para um programa de fidelidade. "
                "O titular pode retirar seu consentimento pelo canal informado pela loja. "*2,
        },format="json")
        self.assertEqual(terms.status_code,201,terms.data)
        self.assertFalse(terms.data.get("cashback_enabled",False))

        page=self.public.get(reverse("public-store-program",kwargs={"slug":self.tenant.slug}))
        self.assertEqual(page.status_code,200,page.data)
        self.assertFalse(page.data["benefits_active"])

        # 2. A solicitação pública não libera participação nem benefício.
        payload={
            "name":"Cliente de demonstração","email":"qa@example.invalid",
            "accepted_terms":True,"marketing_opt_in":False,
            "terms_version":"journey-v1",
        }
        with patch("apps.participants.tasks.send_enrollment_email.delay") as mail_queue:
            with self.captureOnCommitCallbacks(execute=True):
                joined=self.public_post("public-store-join",payload,slug=self.tenant.slug)
            self.assertEqual(joined.status_code,202,joined.data)
            self.assertFalse(joined.data["cashback_enabled"])
            self.assertFalse(joined.data["participant_created"])
            self.assertEqual(mail_queue.call_count,1)
        submission=EnrollmentSubmission.objects.get(tenant=self.tenant)
        self.assertEqual(submission.status,"pending_verification")
        self.assertFalse(submission.marketing_opt_in)
        self.assertFalse(ProgramParticipant.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

        # 3. Antes de provar e-mail, a autorização de cliente é recusada.
        approval_path=self.tenant_url(
            "tenant-customer-match-approve",submission_id=submission.id
        )
        with patch("apps.participants.customer_link_approval.read_customer_candidates") as read:
            blocked=self.owner_client.post(approval_path,{
                "customer_id":"351","confirm":True,
            },format="json")
        self.assertEqual(blocked.status_code,409,blocked.data)
        read.assert_not_called()

        # 4. A posse do e-mail é provada uma única vez; ninguém envia e-mail real.
        proof=EnrollmentEmailChallenge.objects.get(
            submission=submission,purpose="verify"
        )
        token=make_token(proof.pk,"verify")
        checked=self.public_post("public-enrollment-email-action",{
            "token":token,"action":"verify",
        })
        self.assertEqual(checked.status_code,200,checked.data)
        self.assertEqual(checked.data["status"],"email_verified")
        self.assertFalse(checked.data["cashback_enabled"])
        self.assertEqual(self.public_post("public-enrollment-email-action",{
            "token":token,"action":"verify",
        }).status_code,410)

        # 5. Somente a conta autorizada da mesma loja permite vínculo.
        customer=[{"id":"351","email":"qa@example.invalid"}]
        with (
            patch("apps.participants.customer_link_preview.config",
                  return_value=self.customer_cfg),
            patch("apps.participants.customer_link_preview.decrypt_token",
                  return_value="synthetic-access-token"),
            patch("apps.participants.customer_link_preview.read_customer_candidates",
                  return_value=customer),
        ):
            preview=self.owner_client.post(self.tenant_url(
                "tenant-customer-match-preview",submission_id=submission.id
            ),{},format="json")
        self.assertEqual(preview.status_code,200,preview.data)
        self.assertEqual(preview.data["customer_id"],"351")
        self.assertFalse(preview.data["participant_created"])

        with (
            patch("apps.participants.customer_link_approval.config",
                  return_value=self.customer_cfg),
            patch("apps.participants.customer_link_approval.decrypt_token",
                  return_value="synthetic-access-token"),
            patch("apps.participants.customer_link_approval.read_customer_candidates",
                  return_value=customer),
        ):
            approved=self.owner_client.post(approval_path,{
                "customer_id":"351","confirm":True,
            },format="json")
        self.assertEqual(approved.status_code,201,approved.data)
        self.assertFalse(approved.data["cashback_enabled"])
        self.assertFalse(approved.data["orders_modified"])
        self.assertEqual(ProgramParticipant.objects.count(),1)
        self.assertEqual(EnrollmentCustomerLink.objects.count(),1)
        participant=ProgramParticipant.objects.get(tenant=self.tenant)

        # Replay idempotente e isolamento entre lojas no painel.
        repeat=self.owner_client.post(approval_path,{
            "customer_id":"351","confirm":True,
        },format="json")
        self.assertEqual(repeat.status_code,200,repeat.data)
        foreign=APIClient()
        foreign.force_authenticate(self.other)
        self.assertEqual(foreign.get(self.tenant_url("tenant-participants")).status_code,404)
        directory=self.owner_client.get(self.tenant_url("tenant-participants"))
        self.assertEqual(directory.status_code,200,directory.data)
        self.assertEqual(directory.data["summary"]["active"],1)
        wallet_url=self.tenant_url(
            "participant-wallet",participant_id=participant.pk
        )
        wallet=self.owner_client.get(wallet_url)
        self.assertEqual(wallet.status_code,200,wallet.data)
        self.assertIsNone(wallet.data["balances"])
        self.assertFalse(wallet.data["redemption_enabled"])
        self.assertEqual(foreign.get(wallet_url).status_code,404)
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

        # 6. O consumidor pode retirar o aceite. O vínculo não vira crédito.
        withdrawal_id=EnrollmentEmailChallenge.objects.create(
            submission=submission,purpose="withdraw",
            expires_at=timezone.now()+__import__("datetime").timedelta(minutes=20),
        )
        withdrawal_id.token_digest=__import__("hashlib").sha256(
            make_token(withdrawal_id.pk,"withdraw").encode("ascii")
        ).hexdigest()
        withdrawal_id.save(update_fields=["token_digest"])
        withdrawn=self.public_post("public-enrollment-email-action",{
            "token":make_token(withdrawal_id.pk,"withdraw"),"action":"withdraw",
        })
        self.assertEqual(withdrawn.status_code,200,withdrawn.data)
        participant.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(participant.status,ProgramParticipant.Status.WITHDRAWN)
        self.assertEqual(submission.status,EnrollmentSubmission.Status.WITHDRAWN)
        self.assertFalse(submission.marketing_opt_in)
        self.assertEqual(self.owner_client.get(wallet_url).status_code,404)
        self.assertEqual(self.owner_client.get(
            self.tenant_url("tenant-participants")
        ).data["summary"]["total"],0)
        self.assertFalse(CashbackEvent.objects.exists())
