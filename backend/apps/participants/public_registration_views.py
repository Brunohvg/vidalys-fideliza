"""Página por loja para solicitação pública de adesão, sem liberar recompensas.

Não autentica comprador por e-mail informado. Gera apenas um registro de
aceite pendente, nunca ProgramParticipant ou evento de ledger.
"""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant
from .enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms
from .enrollment_views import secure, terms_payload, valid_object, _limit_public

PUBLIC_REQUESTS_PER_DAY = 40


def active_terms_for(tenant):
    return ProgramTerms.objects.filter(tenant=tenant, active=True).first()


def is_ready(terms):
    # Texto de privacidade separado é requisito antes da inscrição espontânea.
    return bool(terms and len(terms.privacy_notice.strip()) >= 120)


class PublicStoreProgramView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, slug):
        if not settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED:
            return secure(Response({"detail": "Adesão pública indisponível."}, status=404))
        tenant = get_object_or_404(Tenant, slug=slug, status=Tenant.Status.ACTIVE)
        terms = active_terms_for(tenant)
        if not is_ready(terms):
            return secure(Response({"detail": "Adesão pública ainda não disponível."}, status=404))
        return secure(Response({
            "mode": "public_pre_enrollment",
            "store_name": tenant.name, "store_slug": tenant.slug,
            "terms": terms_payload(terms),
            "identity_verification_required": True,
            "benefits_active": False,
            "note": "A solicitação depende da verificação posterior do cadastro.",
        }))


@method_decorator(csrf_protect, name="dispatch")
class PublicStoreJoinView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, slug):
        if not settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED:
            return secure(Response({"detail": "Adesão pública indisponível."}, status=404))
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas. Tente novamente mais tarde."}, status=429))
        if not valid_object(
            request, ("name", "email", "accepted_terms", "marketing_opt_in", "terms_version")
        ):
            return secure(Response({"detail": "Preencha somente os campos de adesão."}, status=400))
        name = request.data["name"]
        email = request.data["email"]
        version = request.data["terms_version"]
        if (not isinstance(name, str) or not 3 <= len(name.strip()) <= 140
                or any(ord(c) < 32 for c in name)
                or not isinstance(email, str) or not 3 <= len(email) <= 254
                or not isinstance(version, str)
                or request.data["accepted_terms"] is not True
                or type(request.data["marketing_opt_in"]) is not bool):
            return secure(Response({"detail": "Confira dados e aceite dos termos."}, status=400))
        email = email.strip().casefold()
        try:
            validate_email(email)
        except ValidationError:
            return secure(Response({"detail": "Informe um e-mail válido."}, status=400))
        tenant = get_object_or_404(
            Tenant.objects.select_for_update(), slug=slug, status=Tenant.Status.ACTIVE
        )
        terms = active_terms_for(tenant)
        if not is_ready(terms):
            return secure(Response({"detail": "Adesão pública ainda não disponível."}, status=404))
        if version != terms.version:
            return secure(Response({"detail": "O regulamento mudou. Leia a versão atual."}, status=409))

        # Limite transacional por loja; PII de cadastros falsos não entra em carteira.
        now = timezone.now()
        recent = EnrollmentSubmission.objects.filter(
            tenant=tenant, accepted_at__gte=now - timedelta(days=1)
        ).count()
        if recent >= PUBLIC_REQUESTS_PER_DAY:
            return secure(Response({"detail": "Limite de solicitações atingido."}, status=429))

        already = EnrollmentSubmission.objects.filter(
            tenant=tenant, email__iexact=email,
            status=EnrollmentSubmission.Status.PENDING_VERIFICATION
        ).exists()
        if not already:
            # Convite interno usado imediatamente. Nenhum token é devolvido.
            import secrets
            from .enrollment_views import digest
            token = secrets.token_urlsafe(32)
            invitation = EnrollmentInvite.objects.create(
                tenant=tenant, terms=terms,
                token_digest=digest(token), created_by=None,
                expires_at=now + timedelta(hours=24), consumed_at=now,
            )
            consent_text = (terms.body + "\n" + terms.privacy_notice).encode("utf-8")
            EnrollmentSubmission.objects.create(
                tenant=tenant, invitation=invitation, terms=terms,
                name=name.strip(), email=email, accepted_at=now,
                marketing_opt_in=request.data["marketing_opt_in"],
                terms_digest=hashlib.sha256(consent_text).hexdigest(),
            )
        # A mesma resposta evita revelar se um e-mail já está na fila.
        return secure(Response({
            "status": "pending_verification", "participant_created": False,
            "cashback_enabled": False,
            "terms_version": terms.version,
            "message": "Solicitação recebida. A loja ainda precisa confirmar seu cadastro.",
        }, status=202))
