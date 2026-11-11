"""API de prévia estritamente read-only, autenticada e com limite de amostra."""
import json

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.costs.models import CostItem
from apps.tenants.models import TenantMembership

from .reconciliation import InvalidSnapshot, MAX_SNAPSHOT_BYTES, reconcile_products


class CatalogReconcilePreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_id):
        # Evitar vazamento até da existência de outras lojas.
        get_object_or_404(TenantMembership, user=request.user, tenant_id=tenant_id)
        if not isinstance(request.data, dict) or set(request.data) != {"products"}:
            return Response({"detail": "Informe somente products como array JSON."}, status=400)
        raw_size = len(json.dumps(request.data, ensure_ascii=False).encode("utf-8"))
        if raw_size > MAX_SNAPSHOT_BYTES:
            return Response({"detail": "Amostra excede 150 KB."}, status=413)
        products = request.data["products"]
        # Select somente da loja autorizada; sem métodos de escrita.
        local = list(CostItem.objects.filter(tenant_id=tenant_id).only(
            "id", "external_variant_id", "sku", "reference",
            "unit_cost_cents", "selling_price_cents", "verified_at",
        ))
        try:
            result = reconcile_products(products, local)
        except InvalidSnapshot as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result)
