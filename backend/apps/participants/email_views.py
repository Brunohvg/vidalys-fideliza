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
from .email_proof import consume_challenge, enqueue_confirmation, email_links_enabled
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
        return secure(Response({
            "status": status_value,
            "identity_verified_in_nuvemshop": False,
            "participant_created": False,
            "cashback_enabled": False,
            "message": (
                "Solicitação retirada. Nenhuma recompensa foi criada."
                if action == "withdraw"
                else "E-mail confirmado. A loja ainda precisa validar o cadastro na Nuvemshop."
            ),
        }))
