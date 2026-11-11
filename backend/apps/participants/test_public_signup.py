"""Registro espontâneo por loja: teste de termos, privacidade e não concessão."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackWallet
from .models import ProgramParticipant
from .enrollment_models import ProgramTerms, EnrollmentInvite, EnrollmentSubmission


PRIVACY_NOTICE = (
    "A loja é responsável pelo uso dos dados pessoais fornecidos. "
    "O nome e e-mail são coletados para registrar o interesse no programa, "
    "validar a identidade do titular e responder à solicitação. "
    "O titular poderá exercer direitos de acesso, correção e eliminação "
    "pelos canais oficiais informados pela própria loja."
)


class StorePublicEnrollmentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="public-store-owner")
        self.tenant = Tenant.objects.create(
            name="Loja Jardim", slug="loja-jardim", status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner")
        self.client = APIClient()
        self.data = {
            "name": "Compradora de exemplo", "email": "teste@example.invalid",
            "accepted_terms": True, "marketing_opt_in": False,
            "terms_version": "v1",
        }
        self.terms_fields = {
            "version": "v1", "title": "Regras para adesão voluntária",
            "body": "Este regulamento apresenta regras ilustrativas para testes de adesão. "
                    "Não há desconto, pontos ou cashback ativo na etapa de homologação.",
            "privacy_notice": PRIVACY_NOTICE,
        }

    def terms(self, with_privacy=True):
        owner = APIClient()
        owner.force_authenticate(self.owner)
        data = dict(self.terms_fields)
        if not with_privacy:
            data.pop("privacy_notice")
        response = owner.post(
            reverse("tenant-program-terms",kwargs={"tenant_id":self.tenant.pk}),
            data,format="json",
        )
        self.assertEqual(response.status_code,201,response.data)
        return response

    def page(self):
        return reverse("public-store-program",kwargs={"slug":self.tenant.slug})

    def join(self):
        return reverse("public-store-join",kwargs={"slug":self.tenant.slug})

    def test_only_approved_active_store_with_privacy_is_visible(self):
        self.assertEqual(self.client.get(self.page()).status_code,404)
        self.terms(with_privacy=False)
        self.assertEqual(self.client.get(self.page()).status_code,404)
        self.tenant.status=Tenant.Status.DRAFT
        self.tenant.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.page()).status_code,404)

    def test_public_page_and_pendings_not_real_member(self):
        self.terms()
        response=self.client.get(self.page())
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["store_name"],"Loja Jardim")
        self.assertIn("A loja é responsável",response.data["terms"]["privacy_notice"])
        self.assertFalse(response.data["benefits_active"])
        self.assertEqual(response["Cache-Control"],"private, no-store")
        request=self.client.post(self.join(),self.data,format="json")
        self.assertEqual(request.status_code,202,request.data)
        self.assertFalse(request.data["participant_created"])
        self.assertFalse(request.data["cashback_enabled"])
        self.assertEqual(EnrollmentSubmission.objects.count(),1)
        self.assertTrue(EnrollmentInvite.objects.get().consumed_at)
        self.assertIsNone(EnrollmentInvite.objects.get().created_by)
        self.assertFalse(ProgramParticipant.objects.exists())
        self.assertFalse(CashbackWallet.objects.exists())
        saved=EnrollmentSubmission.objects.get()
        self.assertEqual(saved.terms.version,"v1")
        self.assertFalse(saved.marketing_opt_in)
        self.assertEqual(saved.terms_digest.__len__(),64)

    def test_duplicate_email_does_not_create_another_request(self):
        self.terms()
        first=self.client.post(self.join(),self.data,format="json")
        second=self.client.post(self.join(),{**self.data,"email":"TESTE@example.invalid"},format="json")
        self.assertEqual(first.status_code,202)
        self.assertEqual(second.status_code,202)
        self.assertEqual(first.data,second.data)
        self.assertEqual(EnrollmentSubmission.objects.count(),1)
        self.assertEqual(EnrollmentInvite.objects.count(),1)

    def test_no_accept_no_record(self):
        self.terms()
        for data in [
            {**self.data,"accepted_terms":False},
            {**self.data,"marketing_opt_in":"yes"},
            {**self.data,"terms_version":"v0"},
            {**self.data,"name":"X"},
            {**self.data,"email":"invalido"},
            {**self.data,"status":"active"},
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.join(),data,format="json").status_code,400 if
                                 data.get("terms_version") != "v0" else 409)
        self.assertEqual(EnrollmentSubmission.objects.count(),0)

    def test_only_store_own_terms_are_published(self):
        self.terms()
        other=Tenant.objects.create(name="Outra empresa",slug="outra-empresa",status=Tenant.Status.ACTIVE)
        self.assertEqual(self.client.get(reverse("public-store-program",kwargs={"slug":other.slug})).status_code,404)
        self.assertEqual(self.client.post(reverse("public-store-join",kwargs={"slug":other.slug}),
                                self.data,format="json").status_code,404)

    def test_csrf_is_required_for_anonymous_signup(self):
        self.terms()
        public=APIClient(enforce_csrf_checks=True)
        self.assertEqual(public.post(self.join(),self.data,format="json").status_code,403)
        csrf_init=public.get(reverse("auth-session"))
        self.assertEqual(csrf_init.status_code,200)
        cookie=public.cookies.get("csrftoken")
        self.assertIsNotNone(cookie)
        response=public.post(self.join(),self.data,format="json",HTTP_X_CSRFTOKEN=cookie.value)
        self.assertEqual(response.status_code,202,response.content)
