"""Portal do consumidor: apenas dados de sua adesão e nenhum saldo inventado.

Um link HMAC de uso único autentica uma submissão com e-mail comprovado.
Não usa login do lojista nem permite escolher participant_id na requisição.
"""
import hashlib
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.delivery_tracking import enqueue_email
from apps.sales.models import DiscountRewardDraft
from apps.core.models import EmailDispatch
from apps.tenants.branding_models import TenantBranding
from apps.tenants.models import Tenant
from apps.tenants.settings_views import _display
from .email_proof import digest, email_links_enabled, make_token
from .enrollment_models import (
    EnrollmentSubmission, MemberAccessChallenge, ProgramTerms,
)
from .enrollment_views import _limit_public, secure, terms_payload, valid_object
from .models import ProgramParticipant

LINK_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(hours=12)
SESSION_SUBMISSION = "fideliza_member_submission_id"
SESSION_TENANT = "fideliza_member_tenant_id"
SESSION_EXPIRES = "fideliza_member_expires_ts"
PERMITTED = (
    EnrollmentSubmission.Status.EMAIL_VERIFIED,
    EnrollmentSubmission.Status.LINKED,
    EnrollmentSubmission.Status.MEMBER,
)


def _tenant(slug):
    return get_object_or_404(Tenant, slug=slug, status=Tenant.Status.ACTIVE)


def _generic():
    # Nunca revelar se o e-mail foi inscrito ou se já está vinculado.
    return secure(Response({
        "status": "accepted",
        "message": "Se houver adesão com e-mail confirmado, enviaremos um link privado.",
    }, status=202))


def _is_verified(submission, tenant_id):
    return bool(
        submission and submission.tenant_id == tenant_id
        and submission.email_verified_at is not None
        and submission.withdrawn_at is None
        and submission.status in PERMITTED
    )


def _participant(submission):
    # Cadastro local futuro e vínculos legados da Nuvemshop chegam à mesma tela.
    local = getattr(submission, "participant", None)
    if local is not None:
        return local
    link = getattr(submission, "customer_link", None)
    return link.participant if link else None


class MemberClubPublicView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, slug):
        tenant = _tenant(slug)
        terms = ProgramTerms.objects.filter(tenant=tenant, active=True).first()
        brand = TenantBranding.objects.filter(tenant=tenant).first()
        return secure(Response({
            "store_name": tenant.name,
            "store_slug": tenant.slug,
            "branding": _display(tenant, brand),
            "terms": terms_payload(terms) if terms else None,
            "signup_available": bool(
                settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED and terms
                and len(terms.privacy_notice.strip()) >= 120
            ),
            "points_enabled": False,
            "rewards_enabled": False,
            "redemption_enabled": False,
        }))


@method_decorator(csrf_protect, name="dispatch")
class MemberClubRequestAccessView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, slug):
        tenant = _tenant(slug)
        if not email_links_enabled():
            return secure(Response({"detail": "O acesso por e-mail está indisponível."}, status=503))
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas. Tente novamente depois."}, status=429))
        if not valid_object(request, ("email",)):
            return secure(Response({"detail": "Informe somente seu e-mail."}, status=400))
        email = request.data["email"]
        if not isinstance(email, str) or not 3 <= len(email) <= 254:
            return secure(Response({"detail": "Informe um e-mail válido."}, status=400))
        email = email.strip().casefold()
        try:
            validate_email(email)
        except ValidationError:
            return secure(Response({"detail": "Informe um e-mail válido."}, status=400))

        key_hash = hashlib.sha256(
            (settings.SECRET_KEY + ":" + str(tenant.id) + ":" + email).encode()
        ).hexdigest()
        if not cache.add("fideliza:club:access:" + key_hash, 1, timeout=180):
            return _generic()
        submission = EnrollmentSubmission.objects.filter(
            tenant=tenant, email__iexact=email, withdrawn_at__isnull=True,
            email_verified_at__isnull=False, status__in=PERMITTED,
        ).order_by("-accepted_at").first()
        if submission is None:
            return _generic()
        if MemberAccessChallenge.objects.filter(
            submission=submission, expires_at__gt=timezone.now(),
            consumed_at__isnull=True,
        ).exists():
            return _generic()
        challenge_id = uuid.uuid4()
        token = make_token(challenge_id, "member")
        challenge = MemberAccessChallenge.objects.create(
            id=challenge_id, submission=submission,
            token_digest=digest(token), expires_at=timezone.now() + LINK_TTL,
        )
        from .tasks import send_member_access_email
        enqueue_email(EmailDispatch.Kind.MEMBER, challenge.id, send_member_access_email,
                      str(challenge.id))
        return _generic()


@method_decorator(csrf_protect, name="dispatch")
class MemberClubConfirmAccessView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, slug):
        tenant = _tenant(slug)
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas."}, status=429))
        if not valid_object(request, ("token",)):
            return secure(Response({"detail": "Link inválido."}, status=400))
        token = request.data["token"]
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
            return secure(Response({"detail": "Link inválido."}, status=400))
        challenge = MemberAccessChallenge.objects.select_for_update().select_related(
            "submission__tenant"
        ).filter(
            token_digest=digest(token), consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
            submission__tenant_id=tenant.id,
        ).first()
        if not challenge or not _is_verified(challenge.submission, tenant.id):
            return secure(Response({"detail": "Link usado ou expirado."}, status=410))
        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["consumed_at"])
        # Impede fixação de sessão; a sessão de lojista nunca dá acesso ao consumidor.
        request.session.cycle_key()
        request.session[SESSION_SUBMISSION] = str(challenge.submission_id)
        request.session[SESSION_TENANT] = str(tenant.id)
        request.session[SESSION_EXPIRES] = int((timezone.now() + SESSION_TTL).timestamp())
        return secure(Response({"authenticated": True, "store_slug": tenant.slug}))


def _authorized_submission(request, tenant):
    if request.session.get(SESSION_TENANT) != str(tenant.id):
        return None
    expires = request.session.get(SESSION_EXPIRES)
    if type(expires) is not int or expires <= int(timezone.now().timestamp()):
        return None
    sid = request.session.get(SESSION_SUBMISSION)
    if not isinstance(sid, str):
        return None
    try:
        sid = uuid.UUID(sid)
    except (ValueError, AttributeError):
        return None
    submission = EnrollmentSubmission.objects.select_related("terms").filter(
        pk=sid, tenant=tenant,
    ).first()
    return submission if _is_verified(submission, tenant.id) else None


class MemberClubMeView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, slug):
        tenant = _tenant(slug)
        submission = _authorized_submission(request, tenant)
        if not submission:
            return secure(Response({"detail": "Faça login para acessar seu clube."}, status=401))
        participant = _participant(submission)
        if participant and (
            participant.tenant_id != tenant.id
            or participant.status == ProgramParticipant.Status.WITHDRAWN
        ):
            participant = None
        active = bool(participant and participant.status == ProgramParticipant.Status.ACTIVE)
        # Somente catálogo publicado pelo tenant. A carteira permanece desativada,
        # sem assumir saldo, elegibilidade ou existência de cupom.
        catalog = DiscountRewardDraft.objects.filter(
            tenant=tenant,
            publication_status=DiscountRewardDraft.PublicationStatus.PUBLISHED,
        ).order_by("points_cost", "created_at", "id")[:30]
        published_rewards = [
            {
                "id":str(item.id),"title":item.title,
                "points_cost":item.points_cost,"discount_cents":item.discount_cents,
                "min_order_cents":item.min_order_cents,"status":"locked",
                "points_missing":None,"redemption_enabled":False,
            }
            for item in catalog
        ]
        return secure(Response({
            "store_name": tenant.name,
            "display_name": submission.name,
            "status": "active" if active else (
                "paused" if participant else "awaiting_link"
            ),
            "joined_at": participant.joined_at.isoformat() if participant else None,
            "terms": terms_payload(submission.terms),
            "points_balance": None,
            "points_pending": None,
            "points_status": "not_active",
            "available_rewards": published_rewards,
            "transactions": [],
            "redemption_enabled": False,
            "orders_verified": False,
            "note": "As recompensas publicadas são apenas para consulta. Pontos e resgates ainda não estão ativos; nenhum cupom é gerado.",
        }))


@method_decorator(csrf_protect, name="dispatch")
class MemberClubLogoutView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request, slug):
        _tenant(slug)
        for key in (SESSION_SUBMISSION, SESSION_TENANT, SESSION_EXPIRES):
            request.session.pop(key, None)
        return secure(Response({"authenticated": False}))
