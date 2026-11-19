"""Perfil do cliente no Meu Clube, cópia dos dados e o app instalável.

Tudo exige a sessão do próprio cliente (link ou código do e-mail), exceto o
manifest e o ícone do app, que só têm nome e cores públicos da loja.
"""
import json
from datetime import date
from html import escape

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.branding_models import TenantBranding
from apps.tenants.settings_views import _display
from .enrollment_models import EnrollmentSubmission
from .enrollment_views import secure
from .member_portal_views import _authorized_submission, _ledger_snapshot, _participant, _tenant
from .models import ProgramParticipant
from .phone import PhoneConflict, assign_phone, phone_digests, phone_fields, normalize_br_phone

PROFILE_FIELDS = {"name", "phone", "birth_day", "birth_month", "marketing_opt_in"}


def _owned_participant(submission, tenant):
    participant = _participant(submission)
    if participant and participant.tenant_id == tenant.id and participant.status != ProgramParticipant.Status.WITHDRAWN:
        return participant
    return None


def _profile(submission, participant):
    return {
        "display_name": submission.name, "email": submission.email,
        "phone_last4": (participant.phone_last4 if participant else "") or submission.phone_last4,
        "birth_day": submission.birth_day, "birth_month": submission.birth_month,
        "marketing_opt_in": submission.marketing_opt_in,
    }


@method_decorator(csrf_protect, name="dispatch")
class MemberProfileView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["patch", "options"]

    @transaction.atomic
    def patch(self, request, slug):
        tenant = _tenant(slug)
        found = _authorized_submission(request, tenant)
        if not found:
            return secure(Response({"detail": "Faça login para editar seu perfil."}, status=401))
        submission = EnrollmentSubmission.objects.select_for_update().get(pk=found.pk)
        data = request.data
        if not isinstance(data, dict) or not data or not set(data) <= PROFILE_FIELDS:
            return secure(Response({"detail": "Envie apenas os dados do perfil."}, status=400))
        participant = _owned_participant(submission, tenant)
        fields = []

        if "name" in data:
            name = data["name"].strip() if isinstance(data["name"], str) else ""
            if not 3 <= len(name) <= 140:
                return secure(Response({"detail": "Informe seu nome com pelo menos 3 letras."}, status=400))
            submission.name = name
            fields.append("name")
            if participant:
                participant.display_name = name[:140]
                participant.save(update_fields=["display_name"])

        if "birth_day" in data or "birth_month" in data:
            day, month = data.get("birth_day"), data.get("birth_month")
            if day is None and month is None:
                submission.birth_day = submission.birth_month = None
            else:
                try:
                    if type(day) is not int or type(month) is not int:
                        raise ValueError
                    date(2000, month, day)
                except (ValueError, TypeError):
                    return secure(Response({"detail": "Data de aniversário inválida."}, status=400))
                submission.birth_day, submission.birth_month = day, month
            fields += ["birth_day", "birth_month"]

        if "marketing_opt_in" in data:
            if type(data["marketing_opt_in"]) is not bool:
                return secure(Response({"detail": "Preferência inválida."}, status=400))
            submission.marketing_opt_in = data["marketing_opt_in"]
            fields.append("marketing_opt_in")

        if "phone" in data:
            raw = data["phone"]
            if not isinstance(raw, str):
                return secure(Response({"detail": "Celular inválido."}, status=400))
            raw = raw.strip()
            try:
                if raw == "":
                    submission.phone_digest, submission.phone_last4 = "", ""
                    if participant:
                        assign_phone(participant, "")
                else:
                    digest, last4 = phone_fields(tenant_id=tenant.id, raw=raw)
                    if participant:
                        assign_phone(participant, raw)
                    elif ProgramParticipant.objects.filter(
                        tenant=tenant, phone_digest__in=phone_digests(
                            tenant_id=tenant.id, e164=normalize_br_phone(raw)),
                    ).exists():
                        raise PhoneConflict("Este celular já está em outro cadastro do clube.")
                    submission.phone_digest, submission.phone_last4 = digest, last4
            except PhoneConflict as exc:
                return secure(Response({"detail": str(exc)}, status=409))
            except ValueError as exc:
                return secure(Response({"detail": str(exc)}, status=400))
            fields += ["phone_digest", "phone_last4"]

        submission.save(update_fields=sorted(set(fields)))
        return secure(Response({"profile": _profile(submission, participant), "updated": True}))


class MemberExportView(APIView):
    """Cópia dos dados do próprio cliente (LGPD, art. 18)."""
    permission_classes = [AllowAny]
    http_method_names = ["get", "options"]

    def get(self, request, slug):
        tenant = _tenant(slug)
        submission = _authorized_submission(request, tenant)
        if not submission:
            return secure(Response({"detail": "Faça login para baixar seus dados."}, status=401))
        participant = _owned_participant(submission, tenant)
        ledger = _ledger_snapshot(tenant, participant) if participant else None
        payload = {
            "loja": tenant.name,
            "gerado_em": timezone.now().isoformat(),
            "perfil": _profile(submission, participant),
            "adesao": {
                "aceite_em": submission.accepted_at.isoformat(),
                "regulamento_versao": submission.terms.version if submission.terms_id else None,
                "email_confirmado_em": submission.email_verified_at.isoformat() if submission.email_verified_at else None,
                "situacao": participant.status if participant else "aguardando_loja",
            },
            "pontos": {
                "saldo": ledger["points_balance"] if ledger else None,
                "pendentes": ledger["points_pending"] if ledger else None,
                "extrato": ledger["transactions"] if ledger else [],
            },
            "observacao": "O celular é guardado apenas cifrado; mostramos só os 4 últimos dígitos.",
        }
        response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2),
                                content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="meus-dados-clube.json"'
        return secure(response)


def _ink(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    luminance = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "#24113F" if luminance > 0.4 else "#FFFFFF"


def _brand(tenant):
    return _display(tenant, TenantBranding.objects.filter(tenant=tenant).first())


class ClubManifestView(APIView):
    """Manifest do app do clube: nome e cores da loja, abre direto no Meu Clube."""
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, slug):
        tenant = _tenant(slug)
        brand = _brand(tenant)
        name = brand["program_name"][:45]
        icon = f"/api/v1/public/clubs/{tenant.slug}/icon.svg"
        manifest = {
            "id": f"/clube/{tenant.slug}",
            "name": name,
            "short_name": name if len(name) <= 14 else tenant.name[:14],
            "description": f"Pontos e benefícios da {tenant.name[:60]}",
            "lang": "pt-BR",
            "start_url": f"/clube/{tenant.slug}?origem=app",
            "scope": "/clube/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#F8F9FF",
            "theme_color": brand["primary_color"],
            "icons": [
                {"src": icon, "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
                {"src": icon + "?maskable=1", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"},
                {"src": "/club-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/club-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            ],
        }
        response = HttpResponse(json.dumps(manifest, ensure_ascii=False),
                                content_type="application/manifest+json; charset=utf-8")
        response["Cache-Control"] = "public, max-age=300"
        return response


class ClubIconView(APIView):
    """Ícone do app: iniciais da loja sobre a cor principal."""
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, slug):
        tenant = _tenant(slug)
        brand = _brand(tenant)
        primary, accent = brand["primary_color"], brand["accent_color"]
        letters = "".join(w[0] for w in tenant.name.split()[:2]).upper() or "C"
        maskable = request.query_params.get("maskable") == "1"
        radius = 0 if maskable else 112
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            f'<rect width="512" height="512" rx="{radius}" fill="{escape(primary)}"/>'
            f'<circle cx="400" cy="112" r="56" fill="{escape(accent)}" opacity=".9"/>'
            f'<text x="256" y="300" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-weight="800" '
            f'font-size="{150 if maskable else 180}" fill="{_ink(primary)}">{escape(letters[:2])}</text>'
            '</svg>'
        )
        response = HttpResponse(svg, content_type="image/svg+xml")
        response["Cache-Control"] = "public, max-age=300"
        return response


@method_decorator(csrf_protect, name="dispatch")
class MemberCouponView(APIView):
    """Cliente gera o cupom único para usar no site (giftback: todo o crédito; pontos: a recompensa)."""
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request, slug):
        from apps.sales.online import CouponUnavailable, issue_coupon, present_coupon
        tenant = _tenant(slug)
        found = _authorized_submission(request, tenant)
        if not found:
            return secure(Response({"detail": "Faça login para gerar seu cupom."}, status=401))
        participant = _owned_participant(found, tenant)
        if participant is None or participant.status != ProgramParticipant.Status.ACTIVE:
            return secure(Response({"detail": "Sua participação ainda não está ativa."}, status=409))
        data = request.data if isinstance(request.data, dict) else None
        if data is None or not set(data) <= {"reward_id"}:
            return secure(Response({"detail": "Pedido inválido."}, status=400))
        reward_id = data.get("reward_id")
        if reward_id is not None and (not isinstance(reward_id, str) or len(reward_id) > 40):
            return secure(Response({"detail": "Recompensa inválida."}, status=400))
        try:
            coupon = issue_coupon(participant, reward_id=reward_id)
        except CouponUnavailable as exc:
            return secure(Response({"detail": str(exc)}, status=409))
        except (ValueError, PermissionError):
            return secure(Response({"detail": "Não foi possível gerar o cupom agora."}, status=409))
        return secure(Response({"coupon": present_coupon(coupon)}, status=201))
