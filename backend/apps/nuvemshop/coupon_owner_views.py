"""Advisory owner lookup for authenticated store administrators only.

Not exposed to anonymous storefront scripts: such scripts could forge a
customer_id and reveal whether a shopper owns a reward. Integration with a
checkout-side trusted identity is a separate, currently UNVERIFIED gate.
"""
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.tenants.models import TenantMembership
from apps.customers.models import ChannelCustomerReference
from .models import NuvemshopCouponIntent
from .order_readonly import safe_id


class CouponValidateOwnerView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request):
        data = request.data
        if not isinstance(data, dict) or set(data) != {
            "tenant_id", "coupon_id", "customer_id",
        }:
            return Response({"detail":"Parâmetros inválidos"},status=400)
        tenant_id = data.get("tenant_id")
        member = get_object_or_404(
            TenantMembership.objects.select_related("tenant"),
            tenant_id=tenant_id,user=request.user,
            role__in=(TenantMembership.Role.OWNER,TenantMembership.Role.ADMIN),
        )
        coupon_id, customer_id = safe_id(data["coupon_id"]), safe_id(data["customer_id"])
        if coupon_id is None or customer_id is None:
            return Response({"detail":"Identificador inválido"},status=400)
        intent = NuvemshopCouponIntent.objects.select_related("voucher").filter(
            tenant=member.tenant, remote_coupon_id=coupon_id,
            store_id=member.tenant.external_store_id,
            state=NuvemshopCouponIntent.State.ISSUED,
        ).first()
        reference = ChannelCustomerReference.objects.filter(
            tenant=member.tenant,channel="nuvemshop",external_id=customer_id,
        ).first()
        matched = bool(intent and reference and
                       reference.profile.participant_id == intent.voucher.participant_id)
        response = Response({
            "mode":"advisory_only", "matched":matched,
            "may_apply_discount":False,
            "preventive_checkout_enforced":False,
            "reason":"A Admin API do cupom não vincula desconto ao cliente no checkout.",
        })
        response["Cache-Control"] = "private, no-store"
        return response
