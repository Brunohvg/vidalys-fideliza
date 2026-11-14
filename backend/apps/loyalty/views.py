"""Vouchers: autorizações HTTP apenas; operações/ledger exclusivamente em services."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.channels.services import authenticate_flow_key
from apps.participants.member_portal_views import (
    _authorized_submission, _participant,
)
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership

from .services import (
    LoyaltyBlocked, issue_voucher, redeem_voucher, verify_voucher,
)


def _reply(payload, status=200):
    response = Response(payload, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


def _operator(request, tenant_id):
    # O canal é derivado da autenticação, jamais aceito do JSON.
    if request.user and request.user.is_authenticated:
        if TenantMembership.objects.filter(
            tenant_id=tenant_id, user=request.user,
            role__in=(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN),
            tenant__status=Tenant.Status.ACTIVE,
        ).exists():
            return "counter"
        return None
    credential = authenticate_flow_key(
        tenant_id=tenant_id, authorization=request.headers.get("Authorization", ""),
    )
    return "vidalys_flow" if credential else None


class VoucherCheckView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "orders_ingest"
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id):
        if not _operator(request, tenant_id):
            return _reply({"detail": "Credencial não autorizada."}, 403)
        if not settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED:
            return _reply({"detail": "Resgate ainda não está disponível."}, 409)
        if not isinstance(request.data, dict) or set(request.data) != {"code"}:
            return _reply({"detail": "Informe código do voucher."}, 400)
        try:
            result = verify_voucher(tenant_id=tenant_id, code=request.data["code"])
        except LoyaltyBlocked:
            result = {"valid": False, "reason": "invalid_code"}
        return _reply(result)


class VoucherRedeemView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "orders_ingest"
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id):
        channel = _operator(request, tenant_id)
        if not channel:
            return _reply({"detail": "Credencial não autorizada."}, 403)
        if not isinstance(request.data, dict) or set(request.data) != {
            "code", "redemption_reference",
        }:
            return _reply({"detail": "Código e referência obrigatórios."}, 400)
        try:
            voucher, redeemed = redeem_voucher(
                tenant_id=tenant_id, code=request.data["code"], channel=channel,
                external_receipt=request.data["redemption_reference"],
            )
        except PermissionError:
            return _reply({"detail": "Resgate não habilitado."}, 409)
        except LoyaltyBlocked as exc:
            return _reply({"detail": str(exc)}, 409)
        return _reply({
            "redeemed": redeemed, "already_redeemed": not redeemed,
            "voucher_id": str(voucher.pk), "discount_cents": voucher.discount_cents,
            "unit": voucher.unit, "currency": "BRL",
            "external_coupon_created": False,
        })


@method_decorator(csrf_protect, name="dispatch")
class ClubVoucherIssueView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "orders_ingest"
    http_method_names = ["post", "options"]

    def post(self, request, slug):
        if not settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED:
            return _reply({"detail": "Resgate ainda não está disponível."}, 409)
        tenant = get_object_or_404(Tenant, slug=slug, status=Tenant.Status.ACTIVE)
        submission = _authorized_submission(request, tenant)
        if not submission:
            return _reply({"detail": "Faça login para consultar seu clube."}, 401)
        participant = _participant(submission)
        if not participant or participant.status != ProgramParticipant.Status.ACTIVE:
            return _reply({"detail": "Participante inativo."}, 403)
        if not isinstance(request.data, dict) or set(request.data) != {"unit", "amount"}:
            return _reply({"detail": "Informe unidade e quantidade."}, 400)
        if type(request.data["amount"]) is not int:
            return _reply({"detail": "Quantidade inteira obrigatória."}, 400)
        try:
            voucher, code = issue_voucher(
                tenant_id=tenant.pk, participant_id=participant.pk,
                unit=request.data["unit"], amount=request.data["amount"],
            )
        except (PermissionError, LoyaltyBlocked):
            return _reply({"detail": "Saldo não elegível para resgate."}, 409)
        return _reply({
            "code": code, "voucher_id": str(voucher.pk),
            "discount_cents": voucher.discount_cents,
            "expires_at": voucher.expires_at.isoformat(),
            "external_coupon_created": False,
        }, 201)
