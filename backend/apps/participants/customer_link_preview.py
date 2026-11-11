"""Prévia limitada de vínculo de solicitação verificada à conta oficial da loja.

Nenhuma gravação de participante ou saldo; jamais usar e-mail não confirmado.
"""
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.nuvemshop.customer_lookup import (
    CustomerReadError, exact_email_match, read_customer_candidates,
)
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.scopes import has_customer_access
from apps.nuvemshop.security import OAuthConfigurationError, config, decrypt_token
from apps.tenants.models import TenantMembership
from .enrollment_models import EnrollmentSubmission
from .enrollment_views import secure


class CustomerLinkPreviewView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id, submission_id):
        membership = get_object_or_404(TenantMembership.objects.select_related("tenant"),
                                       tenant_id=tenant_id, user=request.user)
        if membership.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
            return secure(Response({"detail": "Operação restrita ao administrador."}, status=403))
        if not isinstance(request.data, dict) or request.data:
            return secure(Response({"detail": "Prévia não recebe dados de clientes."}, status=400))
        if not settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED:
            return secure(Response({
                "detail": "Prévia de clientes desabilitada até autorização read_customers."
            }, status=409))
        submission = get_object_or_404(EnrollmentSubmission,
                                       tenant_id=tenant_id, pk=submission_id)
        if (submission.status != EnrollmentSubmission.Status.EMAIL_VERIFIED
                or not submission.email_verified_at
                or submission.withdrawn_at is not None):
            return secure(Response({
                "detail": "O e-mail precisa estar confirmado e a solicitação ativa."
            }, status=409))
        try:
            cfg = config()
        except OAuthConfigurationError:
            return secure(Response({"detail": "OAuth da Nuvemshop indisponível."}, status=503))
        installed = NuvemshopInstallation.objects.filter(
            tenant_id=tenant_id, client_id=cfg.client_id
        ).first()
        if (installed is None or membership.tenant.platform != "nuvemshop"
                or not membership.tenant.external_store_id
                or installed.store_id != membership.tenant.external_store_id
                or not has_customer_access(installed.scope, customer_preview_enabled=True)):
            return secure(Response({
                "detail": "Esta loja precisa reautorizar read_customers na Nuvemshop."
            }, status=409))

        throttle_key = f"fideliza:customer-match-preview:{tenant_id}:{submission_id}"
        if not cache.add(throttle_key, 1, timeout=60):
            return secure(Response({"detail": "Prévia recente. Tente novamente depois."},
                                   status=429))
        try:
            token = decrypt_token(installed.token_ciphertext, cfg.token_keys)
            data = read_customer_candidates(
                store_id=int(installed.store_id),
                access_token=token,
                user_agent=cfg.user_agent,
                email=submission.email,
            )
            match_status, customer_id = exact_email_match(data, submission.email)
        except OAuthConfigurationError:
            return secure(Response({"detail": "Credencial Nuvemshop indisponível."}, status=503))
        except (CustomerReadError, ValueError):
            return secure(Response({"detail": "Falha na consulta de clientes autorizados."},
                                   status=502))
        return secure(Response({
            "mode": "read_only_customer_match_preview",
            "status": match_status,
            "customer_id": customer_id,
            "email_verified": True,
            "tenant_id": str(tenant_id),
            "submission_id": str(submission_id),
            "scope_required": "read_customers",
            "writes_performed": 0,
            "participant_created": False,
            "cashback_enabled": False,
            "note": "Prévia não cria vínculo nem comprova pedidos, pagamentos ou benefícios.",
        }))
