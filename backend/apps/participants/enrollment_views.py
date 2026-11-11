"""Adesão com aceite explícito, aguardando validação da identidade pela Nuvemshop.

Não cria ProgramParticipant, não atribui cashback e não assume identidade
do comprador apenas pelo e-mail ou posse de um convite.
"""
import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant, TenantMembership
from .enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms
from .email_proof import enqueue_confirmation, email_links_enabled
from .enrollment_models import EnrollmentEmailChallenge


INVITATION_TTL = timedelta(hours=24)
MAX_OPEN_INVITES = 30
MAX_INVITES_PER_DAY = 60


def secure(response):
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def member_for(request, tenant_id):
    return get_object_or_404(
        TenantMembership.objects.select_related("tenant"),
        tenant_id=tenant_id, user=request.user,
    )


def can_edit(member):
    return member.role in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


def digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def terms_payload(item):
    return {
        "id": str(item.id), "version": item.version, "title": item.title,
        "body": item.body, "privacy_notice": item.privacy_notice,
        "approved_at": item.approved_at.isoformat(),
    }


def valid_object(request, fields):
    return isinstance(request.data, dict) and set(request.data) == set(fields)


class ProgramTermsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        member_for(request, tenant_id)
        terms = ProgramTerms.objects.filter(tenant_id=tenant_id, active=True).first()
        return secure(Response({
            "mode": "approval_required",
            "public_signup_enabled": settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED,
            "terms": terms_payload(terms) if terms else None,
        }))

    @transaction.atomic
    def post(self, request, tenant_id):
        member = member_for(request, tenant_id)
        if not can_edit(member):
            return secure(Response({"detail": "Apenas administrador pode aprovar termos."}, status=403))
        if not isinstance(request.data, dict) or set(request.data) not in (
            {"version", "title", "body"},
            {"version", "title", "body", "privacy_notice"},
        ):
            return secure(Response({"detail": "Envie somente versão, título e termos."}, status=400))
        version = request.data["version"]
        title = request.data["title"]
        body = request.data["body"]
        privacy_notice = request.data.get("privacy_notice", "")
        if (not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", version)
                or not isinstance(title, str) or not 3 <= len(title.strip()) <= 100
                or not isinstance(body, str) or not 80 <= len(body.strip()) <= 4000
                or not isinstance(privacy_notice, str)
                or (privacy_notice and not 120 <= len(privacy_notice.strip()) <= 2500)
                or any(ord(char) == 0 for char in (title + body + privacy_notice))):
            return secure(Response({"detail": "Versão, título ou texto dos termos inválido."}, status=400))
        Tenant.objects.select_for_update().get(pk=tenant_id)
        if ProgramTerms.objects.filter(tenant_id=tenant_id, version=version).exists():
            return secure(Response({"detail": "Esta versão de termos já foi utilizada."}, status=409))
        ProgramTerms.objects.filter(tenant_id=tenant_id, active=True).update(active=False)
        terms = ProgramTerms.objects.create(
            tenant_id=tenant_id, version=version, title=title.strip(), body=body.strip(),
            privacy_notice=privacy_notice.strip(),
            approved_by=request.user, approved_at=timezone.now(),
        )
        return secure(Response({
            "mode": "approval_required", "terms": terms_payload(terms),
            "public_signup_enabled": settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED,
            "message": "Termos registrados; nenhuma campanha ou adesão foi ativada.",
        }, status=201))


class InvitationView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id):
        member = member_for(request, tenant_id)
        if not can_edit(member):
            return secure(Response({"detail": "Apenas administrador pode gerar convites."}, status=403))
        if not settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED:
            return secure(Response({"detail": "Adesão pública ainda bloqueada na homologação."}, status=409))
        if not valid_object(request, ()):
            return secure(Response({"detail": "Este convite não recebe dados de clientes."}, status=400))
        Tenant.objects.select_for_update().get(pk=tenant_id)
        terms = ProgramTerms.objects.filter(tenant_id=tenant_id, active=True).first()
        if terms is None:
            return secure(Response({"detail": "Aprove uma versão dos termos primeiro."}, status=409))
        now = timezone.now()
        created_today = EnrollmentInvite.objects.filter(
            tenant_id=tenant_id, created_at__gte=now - timedelta(days=1)
        ).count()
        if created_today >= MAX_INVITES_PER_DAY:
            return secure(Response({"detail": "Limite diário de convites atingido."}, status=429))
        active_count = EnrollmentInvite.objects.filter(
            tenant_id=tenant_id, consumed_at__isnull=True,
            expires_at__gt=now, terms=terms,
        ).count()
        if active_count >= MAX_OPEN_INVITES:
            return secure(Response({"detail": "Limite de convites abertos atingido."}, status=409))
        token = secrets.token_urlsafe(32)
        invite = EnrollmentInvite.objects.create(
            tenant_id=tenant_id, terms=terms, token_digest=digest(token),
            created_by=request.user, expires_at=now + INVITATION_TTL,
        )
        return secure(Response({
            "mode": "invitation_only", "token": token,
            "expires_at": invite.expires_at.isoformat(),
            "participant_created": False, "cashback_enabled": False,
            "note": "O convite comprova somente o aceite, não a identidade na Nuvemshop.",
        }, status=201))


class PendingEnrollmentsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id):
        member = member_for(request, tenant_id)
        if not can_edit(member):
            return secure(Response({"detail": "Apenas administrador pode consultar aceites."}, status=403))
        queryset = EnrollmentSubmission.objects.filter(tenant_id=tenant_id).exclude(
            status=EnrollmentSubmission.Status.WITHDRAWN
        )
        items = [{
            "id": str(item.id), "name": item.name, "email": item.email,
            "terms_version": item.terms.version,
            "accepted_at": item.accepted_at.isoformat(),
            "marketing_opt_in": item.marketing_opt_in,
            "status": item.status,
        } for item in queryset.select_related("terms")[:20]]
        return secure(Response({
            "mode": "consents_pending_identity_verification",
            "total": queryset.count(), "items": items,
            "note": "Aceite não significa comprador Nuvemshop verificado nem participante ativo.",
        }))


def _token(request):
    token = request.data.get("token")
    if (not isinstance(token, str) or len(token) < 32 or len(token) > 128
            or not re.fullmatch(r"[A-Za-z0-9_-]+", token)):
        return None
    return token


def _limit_public(request):
    # Não confiar em X-Forwarded-For: peer do proxy é deliberadamente conservador.
    peer = request.META.get("REMOTE_ADDR", "")
    suffix = hashlib.sha256((settings.SECRET_KEY + peer).encode("utf-8")).hexdigest()[:28]
    key = f"fideliza:enrollment:public:{suffix}"
    if cache.add(key, 1, timeout=60):
        return False
    try:
        return cache.incr(key) > 60
    except ValueError:
        return False


@method_decorator(csrf_protect, name="dispatch")
class PublicInvitationView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request):
        if not settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED:
            return secure(Response({"detail": "Adesão pública indisponível."}, status=404))
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas. Tente depois."}, status=429))
        if not valid_object(request, ("token",)):
            return secure(Response({"detail": "Convite inválido."}, status=400))
        token = _token(request)
        if token is None:
            return secure(Response({"detail": "Convite inválido."}, status=400))
        invitation = EnrollmentInvite.objects.select_related("tenant", "terms").filter(
            token_digest=digest(token),
        ).first()
        if (not invitation or invitation.consumed_at is not None
                or invitation.expires_at <= timezone.now()
                or not invitation.terms.active):
            return secure(Response({"detail": "Convite inválido ou expirado."}, status=410))
        return secure(Response({
            "mode": "explicit_consent_only",
            "store_name": invitation.tenant.name,
            "terms": terms_payload(invitation.terms),
            "expires_at": invitation.expires_at.isoformat(),
            "identity_verified": False,
            "benefits_active": False,
        }))


@method_decorator(csrf_protect, name="dispatch")
class PublicAcceptView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request):
        if not settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED:
            return secure(Response({"detail": "Adesão pública indisponível."}, status=404))
        if _limit_public(request):
            return secure(Response({"detail": "Muitas tentativas. Tente depois."}, status=429))
        if not valid_object(
            request, ("token", "name", "email", "accepted_terms", "marketing_opt_in")
        ):
            return secure(Response({"detail": "Dados do aceite inválidos."}, status=400))
        token = _token(request)
        name, email = request.data["name"], request.data["email"]
        if (token is None or request.data["accepted_terms"] is not True
                or type(request.data["marketing_opt_in"]) is not bool
                or not isinstance(name, str) or not 3 <= len(name.strip()) <= 140
                or not isinstance(email, str) or len(email) > 254
                or any(ord(char) < 32 for char in (name + email))):
            return secure(Response({"detail": "Confira os dados e o aceite dos termos."}, status=400))
        email = email.strip().casefold()
        try:
            validate_email(email)
        except ValidationError:
            return secure(Response({"detail": "Informe um e-mail válido."}, status=400))
        invitation = EnrollmentInvite.objects.select_for_update().select_related("terms").filter(
            token_digest=digest(token),
        ).first()
        if (invitation is None or invitation.consumed_at is not None
                or invitation.expires_at <= timezone.now()
                or not invitation.terms.active):
            return secure(Response({"detail": "Convite inválido ou já utilizado."}, status=410))
        now = timezone.now()
        terms_digest = hashlib.sha256(
            (invitation.terms.body + ("\n" + invitation.terms.privacy_notice if invitation.terms.privacy_notice else "")).encode("utf-8")
        ).hexdigest()
        receipt = EnrollmentSubmission.objects.create(
            tenant_id=invitation.tenant_id,
            invitation=invitation, terms=invitation.terms,
            name=name.strip(), email=email,
            accepted_at=now, marketing_opt_in=request.data["marketing_opt_in"],
            terms_digest=terms_digest,
        )
        invitation.consumed_at = now
        invitation.save(update_fields=["consumed_at"])
        if email_links_enabled():
            enqueue_confirmation(receipt, EnrollmentEmailChallenge.Purpose.VERIFY)
        return secure(Response({
            "status": "pending_verification",
            "receipt_id": str(receipt.id),
            "terms_version": invitation.terms.version,
            "participant_created": False,
            "cashback_enabled": False,
            "message": "Seu aceite foi registrado. A loja ainda precisa confirmar sua identidade.",
        }, status=201))
