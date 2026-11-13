"""Confirmação por e-mail e retirada da pré-adesão, sem autenticar cliente Nuvemshop."""
import re

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant
from .email_proof import consume_challenge, enqueue_confirmation, email_links_enabled, digest
from .customer_link_auto import auto_link_after_verified_email
from .standalone_activation import activate_standalone_after_email
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission
from .enrollment_views import _limit_public, secure, valid_object


def generic_response():
    # Não revelar existência de uma conta ou solicitação.
    return secure(Response({
        "status": "accepted",
        "message": "Se houver uma solicitação correspondente, enviaremos um link de confirmação.",
    }, status=202))


@method_decorator(csrf_protect, name="dispatch")
class PublicWithdrawalRequestView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, slug):
        if not email_links_enabled():
            return secure(Response({"detail": "Solicitações por e-mail indisponíveis."}, status=503))
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas."}, status=429))
        if not valid_object(request, ("email",)):
            return secure(Response({"detail": "Informe apenas o e-mail da solicitação."}, status=400))
        email = request.data["email"]
        if not isinstance(email, str) or len(email) > 254 or len(email) < 3:
            return secure(Response({"detail": "Informe um e-mail válido."}, status=400))
        email = email.strip().casefold()
        try:
            validate_email(email)
        except ValidationError:
            return secure(Response({"detail": "Informe um e-mail válido."}, status=400))
        tenant = get_object_or_404(Tenant, slug=slug)
        # Limite também por destinatário/loja, para não servir de ferramenta de spam.
        from hashlib import sha256
        digest = sha256((settings.SECRET_KEY + str(tenant.pk) + email).encode()).hexdigest()
        if not cache.add("fideliza:withdraw-request:" + digest, 1, timeout=1800):
            return generic_response()
        submission = EnrollmentSubmission.objects.select_for_update().filter(
            tenant=tenant, email__iexact=email,
            status__in=[
                EnrollmentSubmission.Status.PENDING_VERIFICATION,
                EnrollmentSubmission.Status.EMAIL_VERIFIED,
                EnrollmentSubmission.Status.LINKED,
                EnrollmentSubmission.Status.MEMBER,
            ],
        ).order_by("-accepted_at").first()
        if submission:
            enqueue_confirmation(submission, EnrollmentEmailChallenge.Purpose.WITHDRAW)
        return generic_response()


@method_decorator(csrf_protect, name="dispatch")
class PublicEmailActionView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request):
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas."}, status=429))
        if not valid_object(request, ("token", "action")):
            return secure(Response({"detail": "Link inválido."}, status=400))
        token = request.data["token"]
        action = request.data["action"]
        if (not isinstance(token, str)
                or not 32 <= len(token) <= 128
                or not re.fullmatch(r"[A-Za-z0-9_-]+", token)
                or action not in ("verify", "withdraw")):
            return secure(Response({"detail": "Link inválido."}, status=400))
        status_value = consume_challenge(token, action)
        if status_value is None:
            return secure(Response({"detail": "Link inválido, usado ou expirado."}, status=410))
        auto_linked = (action == "verify" and
                       auto_link_after_verified_email(token) == "linked")
        standalone_linked = (action == "verify" and not auto_linked and
                             activate_standalone_after_email(token))
        participant_created = bool(auto_linked or standalone_linked)
        # A URL do próprio clube só é liberada após token válido consumido.
        # Não identifica o consumidor nem inclui tokens/PII na resposta.
        verified_challenge = (
            EnrollmentEmailChallenge.objects.select_related("submission__tenant")
            .filter(token_digest=digest(token),
                    purpose=EnrollmentEmailChallenge.Purpose.VERIFY,
                    consumed_at__isnull=False)
            .first()
            if action == "verify" else None
        )
        club_slug = (
            verified_challenge.submission.tenant.slug if verified_challenge
            else None
        )
        return secure(Response({
            "status": status_value,
            "identity_verified_in_nuvemshop": bool(auto_linked),
            "participant_created": participant_created,
            "cashback_enabled": False,
            "club_slug": club_slug,
            "message": (
                "Solicitação retirada. Nenhuma recompensa foi criada."
                if action == "withdraw"
                else (
                    "E-mail e cadastro da loja confirmados. Sua participação "
                    "foi registrada; não há recompensas ativas nesta etapa."
                    if auto_linked else
                    "Participação confirmada no clube. Seu e-mail foi validado. "
                    "Pontos e recompensas ainda não estão ativos."
                    if standalone_linked else
                    "E-mail confirmado. Se a verificação automática não concluir "
                    "o vínculo, a loja poderá revisar seu cadastro."
                )
            ),
        }))
