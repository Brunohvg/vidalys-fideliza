"""Vouchers: autorizações HTTP apenas; operações/ledger exclusivamente em services."""
import uuid
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
from apps.tenants.club_address import canonical_slug
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
            "code", "redemption_reference", "sale_id", "capture_evidence_id",
        }:
            return _reply({"detail": "Código, pedido, referência e prova do pagamento obrigatórios."}, 400)
        try:
            sale_id = uuid.UUID(str(request.data["sale_id"]))
            capture_id = uuid.UUID(str(request.data["capture_evidence_id"]))
        except (TypeError, ValueError, AttributeError):
            return _reply({"detail": "IDs de pedido e comprovação inválidos."}, 400)
        try:
            voucher, redeemed = redeem_voucher(
                tenant_id=tenant_id, code=request.data["code"], channel=channel,
                external_receipt=request.data["redemption_reference"],
                sale_id=sale_id,
                capture_evidence_id=capture_id,
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
        tenant = get_object_or_404(Tenant, slug=canonical_slug(slug), status=Tenant.Status.ACTIVE)
        submission = _authorized_submission(request, tenant)
        if not submission:
            return _reply({"detail": "Faça login para consultar seu clube."}, 401)
        participant = _participant(submission)
        if not participant or participant.status != ProgramParticipant.Status.ACTIVE:
            return _reply({"detail": "Participante inativo."}, 403)
        pilot_nuvemshop = (
            tenant.platform == "nuvemshop" and tenant.loyalty_live_enabled
        )
        if pilot_nuvemshop and not getattr(
            settings, "FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED", False
        ):
            return _reply({"detail": "Cupom de loja virtual ainda indisponível."}, 409)
        if not isinstance(request.data, dict) or set(request.data) != {"reward_id"}:
            return _reply({"detail": "Escolha uma recompensa publicada."}, 400)
        try:
            reward_id = uuid.UUID(str(request.data["reward_id"]))
        except (TypeError, ValueError, AttributeError):
            return _reply({"detail": "Identificador de recompensa inválido."}, 400)
        if pilot_nuvemshop:
            from apps.sales.models import DiscountRewardDraft
            reward = DiscountRewardDraft.objects.filter(
                tenant=tenant, pk=reward_id,
                publication_status=DiscountRewardDraft.PublicationStatus.PUBLISHED,
            ).first()
            if not reward or "nuvemshop" not in reward.allowed_channels.split(","):
                return _reply({"detail": "Recompensa indisponível para este checkout."}, 409)
        try:
            voucher, code = issue_voucher(
                tenant_id=tenant.pk, participant_id=participant.pk,
                reward_id=reward_id,
            )
        except (PermissionError, LoyaltyBlocked):
            return _reply({"detail": "Saldo não elegível para resgate."}, 409)
        external = False
        if pilot_nuvemshop:
            from apps.nuvemshop.coupon_service import PilotCouponBlocked, provision_coupon
            try:
                _, code = provision_coupon(voucher_id=voucher.pk, issued_code=code)
                external = True
            except PilotCouponBlocked:
                # Voucher reservado + intenção externa incerta: preservar ambos.
                # Não retornar cupom não confirmado nem repetir POST no retry.
                return _reply({
                    "detail": "Emissão externa requer reconciliação; não tente gerar outro voucher.",
                    "voucher_id": str(voucher.pk),
                }, 503)
        return _reply({
            "code": code, "voucher_id": str(voucher.pk),
            "discount_cents": voucher.discount_cents,
            "expires_at": voucher.expires_at.isoformat(),
            "external_coupon_created": external,
        }, 201)


class ClubVoucherCouponStatusView(APIView):
    """Consulta status de cupom próprio: nenhum dado de outra pessoa/tenant."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    http_method_names = ["get", "options"]

    def get(self, request, slug, voucher_id):
        tenant = get_object_or_404(Tenant, slug=canonical_slug(slug), status=Tenant.Status.ACTIVE)
        submission = _authorized_submission(request, tenant)
        if submission is None:
            return _reply({"detail": "Autenticação obrigatória."}, 401)
        participant = _participant(submission)
        if participant is None or participant.tenant_id != tenant.pk:
            return _reply({"detail": "Acesso não autorizado."}, 403)
        from apps.nuvemshop.models import NuvemshopCouponIntent
        intent = NuvemshopCouponIntent.objects.select_related("voucher").filter(
            voucher_id=voucher_id, tenant=tenant,
            voucher__participant=participant,
        ).first()
        if intent is None:
            return _reply({"detail": "Cupom não encontrado."}, 404)
        if intent.state not in (
            NuvemshopCouponIntent.State.ISSUED,
            NuvemshopCouponIntent.State.APPLIED,
            NuvemshopCouponIntent.State.SETTLED,
        ):
            return _reply({"status": "pending_reconciliation"}, 409)
        from apps.nuvemshop.security import config, decrypt_token
        code = decrypt_token(intent.encrypted_code, config().token_keys)
        return _reply({"status": intent.state, "code": code, "voucher_id": str(voucher_id),
                       "external_coupon_created": True})
