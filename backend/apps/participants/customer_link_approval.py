"""Aprovação explícita e idempotente de cliente com aceite e e-mail verificado.

Apenas OWNER/ADMIN. Reconsulta GET /customers, confirma ID da MESMA loja,
reconfere estado dentro de transação e NÃO concede benefícios nem escreve
na Nuvemshop. Feature flag desligada até homologação e revisão LGPD.
"""
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.nuvemshop.customer_lookup import (
    CustomerReadError, exact_email_match, read_customer_candidates,
)
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.privacy_models import PrivacyWebhookRequest
from apps.nuvemshop.scopes import has_customer_access
from apps.nuvemshop.security import OAuthConfigurationError, config, decrypt_token
from apps.tenants.models import Tenant, TenantMembership

from .enrollment_models import EnrollmentCustomerLink, EnrollmentSubmission
from .enrollment_views import secure
from .models import ProgramParticipant


def _result(link, *, already_linked=False):
    return secure(Response({
        "status": "linked",
        "already_linked": already_linked,
        "participant_id": str(link.participant_id),
        "cashback_enabled": False,
        "orders_modified": False,
        "message": "Cliente vinculado ao programa. Recompensas ainda não estão disponíveis.",
    }, status=200 if already_linked else 201))


class CustomerLinkApproveView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id, submission_id):
        member=get_object_or_404(
            TenantMembership.objects.select_related("tenant"),
            user=request.user, tenant_id=tenant_id,
        )
        if member.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
            return secure(Response({"detail": "Você não pode aprovar participantes."}, status=403))
        if not (settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED and
                settings.FIDELIZA_PARTICIPANT_APPROVAL_ENABLED):
            return secure(Response({"detail": "A aprovação de participantes ainda não está disponível."},
                                   status=409))
        if (not isinstance(request.data, dict) or set(request.data)!={"customer_id","confirm"}
                or request.data.get("confirm") is not True
                or not isinstance(request.data.get("customer_id"), str)
                or not request.data["customer_id"].isascii()
                or not request.data["customer_id"].isdecimal()
                or len(request.data["customer_id"])>18
                or int(request.data["customer_id"])<=0):
            return secure(Response({"detail": "Confirme o cliente consultado antes de aprovar."},
                                   status=400))
        requested_id=str(int(request.data["customer_id"]))
        submission=get_object_or_404(EnrollmentSubmission,
                                     pk=submission_id, tenant_id=tenant_id)
        if submission.status==EnrollmentSubmission.Status.LINKED:
            link=EnrollmentCustomerLink.objects.filter(submission=submission).first()
            if link and link.external_customer_id==requested_id and (
                link.participant.status==ProgramParticipant.Status.ACTIVE):
                return _result(link, already_linked=True)
            return secure(Response({"detail": "Esta solicitação já foi encerrada ou vinculada."},
                                   status=409))
        if (submission.status!=EnrollmentSubmission.Status.EMAIL_VERIFIED
                or submission.email_verified_at is None or submission.withdrawn_at):
            return secure(Response({"detail": "O cliente precisa confirmar seu e-mail antes da aprovação."},
                                   status=409))
        installed=NuvemshopInstallation.objects.filter(tenant_id=tenant_id).first()
        if (installed is None or member.tenant.platform!="nuvemshop"
                or member.tenant.status!=Tenant.Status.ACTIVE
                or not member.tenant.external_store_id
                or installed.store_id!=member.tenant.external_store_id
                or not has_customer_access(installed.scope, customer_preview_enabled=True)):
            return secure(Response({"detail": "Atualize a conexão com sua loja antes de aprovar."},
                                   status=409))
        key=f"fideliza:customer-link-approval:{tenant_id}:{submission_id}"
        if not cache.add(key, 1, timeout=45):
            return secure(Response({"detail": "Aguarde antes de repetir a aprovação."},status=429))
        try:
            cfg=config()
            if installed.client_id!=cfg.client_id:
                return secure(Response({"detail": "A conexão da loja precisa ser atualizada."},
                                       status=409))
            token=decrypt_token(installed.token_ciphertext, cfg.token_keys)
            matches=read_customer_candidates(
                store_id=int(installed.store_id),access_token=token,
                user_agent=cfg.user_agent,email=submission.email,
            )
            state,customer_id=exact_email_match(matches,submission.email)
        except (CustomerReadError,OAuthConfigurationError,ValueError):
            return secure(Response({"detail": "Não foi possível conferir o cliente agora."},
                                   status=502))
        if state!="one_exact_match" or customer_id!=requested_id:
            return secure(Response({"detail": "O cadastro mudou ou não pôde ser confirmado. Consulte novamente."},
                                   status=409))

        # Lock da loja serializa tentativas concorrentes de contas/aceites diferentes.
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant_id)
            fresh=EnrollmentSubmission.objects.select_for_update().get(
                pk=submission_id,tenant_id=tenant_id)
            if fresh.status==EnrollmentSubmission.Status.LINKED:
                link=EnrollmentCustomerLink.objects.filter(submission=fresh).first()
                if link and link.external_customer_id==requested_id and (
                    link.participant.status==ProgramParticipant.Status.ACTIVE):
                    return _result(link,already_linked=True)
                return secure(Response({"detail": "A solicitação já foi encerrada."},status=409))
            if fresh.status!=EnrollmentSubmission.Status.EMAIL_VERIFIED or (
                    fresh.email_verified_at is None or fresh.withdrawn_at):
                return secure(Response({"detail": "Esta solicitação não pode mais ser aprovada."},
                                       status=409))
            if PrivacyWebhookRequest.objects.filter(
                store_id=installed.store_id,
                customer_id=requested_id,
                topic=PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
            ).exists():
                return secure(Response({
                    "detail": "Este cliente tem uma solicitação de privacidade pendente."
                }, status=409))
            # Registros anteriores não são adotados silenciosamente.
            if (EnrollmentCustomerLink.objects.filter(
                    tenant_id=tenant_id,external_customer_id=requested_id).exists()
                or ProgramParticipant.objects.filter(
                    tenant_id=tenant_id,external_customer_id=requested_id).exists()):
                return secure(Response({
                    "detail": "Este cliente já participa ou possui vínculo anterior. Revise o cadastro."
                },status=409))
            participant=ProgramParticipant.objects.create(
                tenant_id=tenant_id,external_customer_id=requested_id,
                display_name=fresh.name,contact_email=fresh.email,
                consent_at=fresh.accepted_at,
                consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
                terms_version=fresh.terms.version,
                status=ProgramParticipant.Status.ACTIVE,
            )
            link=EnrollmentCustomerLink.objects.create(
                tenant_id=tenant_id,submission=fresh,
                participant=participant,external_customer_id=requested_id,
                confirmed_by=request.user,
            )
            fresh.status=EnrollmentSubmission.Status.LINKED
            fresh.save(update_fields=["status"])
        return _result(link)
