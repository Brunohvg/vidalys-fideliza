"""Preferências reais por loja: leitura segura e edição versionada.

Nunca altera escopos OAuth, credenciais, saldo, termos jurídicos ou
publicação do programa. Nenhuma entrada controla HTML/CSS arbitrário.
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .branding_models import TenantBranding, TenantBrandingAudit
from .models import Tenant, TenantMembership


BRANDING_FIELDS = ("program_name", "primary_color", "accent_color", "support_email")
BRANDING_DEFAULTS = {
    "program_name": "",
    "primary_color": "#087F79",
    "accent_color": "#37D5BB",
    "support_email": "",
}


def _snapshot(instance):
    if instance is None:
        return dict(BRANDING_DEFAULTS)
    return {field: getattr(instance, field) for field in BRANDING_FIELDS}


def _display(tenant, branding):
    data = _snapshot(branding)
    data["program_name"] = data["program_name"] or f"Clube {tenant.name[:74]}"
    return data


def _luminance(value):
    rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a,b in zip(linear, (0.2126,0.7152,0.0722)))


def _normalize(raw):
    if not isinstance(raw, dict) or set(raw) != set(BRANDING_FIELDS)|{"expected_version"}:
        raise ValueError("Envie apenas os campos da identidade e a versão esperada.")
    version = raw["expected_version"]
    if type(version) is not int or version < 0:
        raise ValueError("Versão de edição inválida.")
    values = {}
    for field in BRANDING_FIELDS:
        value = raw[field]
        if not isinstance(value, str) or any(ord(c)<32 for c in value):
            raise ValueError("Dados da identidade inválidos.")
        values[field] = value.strip()
    name = values["program_name"]
    if name and (len(name)<3 or len(name)>80):
        raise ValueError("O nome do programa deve ter entre 3 e 80 caracteres.")
    for color_field in ("primary_color", "accent_color"):
        color = values[color_field]
        if not re.fullmatch(r"#[A-Fa-f0-9]{6}", color):
            raise ValueError("Cores devem usar formato hexadecimal de 6 dígitos.")
        values[color_field] = color.upper()
    # A cor principal será usada atrás de textos brancos no botão.
    if (1.05/(_luminance(values["primary_color"])+0.05)) < 4.5:
        raise ValueError("Escolha uma cor principal com contraste suficiente para texto branco.")
    address=values["support_email"]
    if address:
        if len(address)>254:
            raise ValueError("E-mail de suporte muito longo.")
        try:
            validate_email(address)
        except ValidationError:
            raise ValueError("E-mail de suporte inválido.") from None
        values["support_email"] = address.casefold()
    return version, values


def _no_cache(response):
    response["Cache-Control"] = "private, no-store"
    return response


class TenantSettingsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request, tenant_id):
        member = get_object_or_404(
            TenantMembership.objects.select_related("tenant"),
            tenant_id=tenant_id, user=request.user
        )
        brand = TenantBranding.objects.filter(tenant_id=tenant_id).first()
        return _no_cache(Response({
            "tenant_id": str(tenant_id),
            "tenant_name": member.tenant.name,
            "tenant_slug": member.tenant.slug,
            "tenant_status": member.tenant.status,
            "can_edit": member.role in ("owner", "admin"),
            "version": brand.version if brand else 0,
            "branding": _display(member.tenant, brand),
            "public_link": None,
            "features": {
                "public_signup_enabled": settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED,
                "email_delivery_enabled": settings.FIDELIZA_EMAIL_DELIVERY_ENABLED,
                "customer_preview_enabled": settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED,
                "cashback_activation_enabled": False,
                "custom_domain_available": False,
            },
            "note": "A identidade salva não ativa inscrições ou recompensas.",
        }))

    @transaction.atomic
    def patch(self, request, tenant_id):
        member = get_object_or_404(TenantMembership, tenant_id=tenant_id, user=request.user)
        if member.role not in ("owner", "admin"):
            return _no_cache(Response({"detail": "Somente administradores podem alterar a loja."},
                                      status=403))
        try:
            expected, values = _normalize(request.data)
        except ValueError as exc:
            return _no_cache(Response({"detail": str(exc)}, status=400))

        tenant=Tenant.objects.select_for_update().get(pk=tenant_id)
        current=TenantBranding.objects.select_for_update().filter(tenant=tenant).first()
        current_version = current.version if current else 0
        if expected != current_version:
            return _no_cache(Response({
                "detail": "As configurações mudaram. Atualize a página antes de salvar.",
                "current_version": current_version,
            }, status=409))
        before = _snapshot(current)
        if before == values:
            return _no_cache(Response({
                "version": current_version, "branding": _display(tenant, current),
                "updated": False,
            }))
        if current is None:
            current = TenantBranding.objects.create(
                tenant=tenant, version=1, updated_by=request.user, **values
            )
        else:
            for name,value in values.items():
                setattr(current,name,value)
            current.version += 1
            current.updated_by=request.user
            current.save(update_fields=list(BRANDING_FIELDS)+["version","updated_by","updated_at"])
        TenantBrandingAudit.objects.create(
            tenant=tenant, version=current.version, actor=request.user,
            before=before, after=_snapshot(current),
        )
        return _no_cache(Response({
            "version": current.version, "branding": _display(tenant, current),
            "updated": True,
        }))
