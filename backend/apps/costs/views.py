"""Cadastro manual, versionado e isolado por loja. Sem integração externa."""
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership
from .models import CostItem, CostAudit
from .serializers import CostItemSerializer, CostWriteSerializer


def membership_or_404(user, tenant_id):
    return get_object_or_404(
        TenantMembership.objects.select_related("tenant"),
        user=user, tenant_id=tenant_id,
    )


def _can_write(membership):
    return membership.role in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


def _mark_verified(item, data, user):
    if data.get("verify_cost"):
        if item.unit_cost_cents is None:
            raise ValueError("É obrigatório informar o custo antes de confirmar.")
        item.provenance = data["provenance"].strip()
        item.verified_at = timezone.now()
        item.verified_by = user


def _duplicates_response(exc):
    # Não expor detalhes internos de SQL ou outros tenants.
    return Response({"detail": "Identificador ou ID da variante já cadastrado nesta loja."}, status=409)


class CostItemsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id):
        membership_or_404(request.user, tenant_id)
        qs = CostItem.objects.filter(tenant_id=tenant_id).select_related("verified_by")
        summary = qs.aggregate(
            total=Count("id"),
            missing_cost=Count("id", filter=Q(unit_cost_cents__isnull=True)),
            needs_review=Count("id", filter=Q(unit_cost_cents__isnull=False, verified_at__isnull=True)),
            missing_price=Count("id", filter=Q(unit_cost_cents__isnull=False, verified_at__isnull=False, selling_price_cents__isnull=True)),
            ready=Count("id", filter=Q(unit_cost_cents__isnull=False, verified_at__isnull=False, selling_price_cents__isnull=False)),
        )
        term = request.query_params.get("q", "").strip()
        if len(term) > 80:
            return Response({"detail": "Busca limitada a 80 caracteres."}, status=400)
        if term:
            qs = qs.filter(Q(reference__icontains=term) | Q(sku__icontains=term) | Q(name__icontains=term))
        state = request.query_params.get("status", "")
        if state == "missing_cost":
            qs = qs.filter(unit_cost_cents__isnull=True)
        elif state == "needs_review":
            qs = qs.filter(unit_cost_cents__isnull=False, verified_at__isnull=True)
        elif state == "missing_price":
            qs = qs.filter(unit_cost_cents__isnull=False, verified_at__isnull=False, selling_price_cents__isnull=True)
        elif state == "ready_for_simulation":
            qs = qs.filter(unit_cost_cents__isnull=False, verified_at__isnull=False, selling_price_cents__isnull=False)
        elif state:
            return Response({"detail": "Filtro inválido."}, status=400)
        try:
            limit = int(request.query_params.get("limit", "30"))
            offset = int(request.query_params.get("offset", "0"))
        except ValueError:
            return Response({"detail": "Paginação inválida."}, status=400)
        if limit not in range(1, 101) or offset < 0 or offset > 100000:
            return Response({"detail": "Paginação fora dos limites."}, status=400)
        return Response({
            "summary": summary,
            "total_filtered": qs.count(),
            "limit": limit, "offset": offset,
            "items": CostItemSerializer(qs.order_by("name", "reference")[offset:offset+limit], many=True).data,
            "data_status": "manual_only",
        })

    def post(self, request, tenant_id):
        member = membership_or_404(request.user, tenant_id)
        if not _can_write(member):
            return Response({"detail": "Permissão somente leitura."}, status=403)
        serializer = CostWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("reference") or not data.get("name"):
            return Response({"detail": "Informe referência e nome do item."}, status=400)
        if "expected_version" in data:
            return Response({"detail": "Versão é usada apenas na atualização."}, status=400)
        if data.get("verify_cost") and data.get("unit_cost_cents") is None:
            return Response({"detail": "Custo obrigatório para confirmação."}, status=400)
        try:
            with transaction.atomic():
                item = CostItem.objects.create(
                    tenant_id=tenant_id,
                    reference=data["reference"], name=data["name"],
                    sku=data.get("sku", ""), external_variant_id=data.get("external_variant_id", ""),
                    unit_cost_cents=data.get("unit_cost_cents"),
                    selling_price_cents=data.get("selling_price_cents"),
                    provenance=data.get("provenance", ""),
                    created_by=request.user, updated_by=request.user,
                )
                _mark_verified(item, data, request.user)
                if data.get("verify_cost"):
                    item.save(update_fields=["provenance", "verified_at", "verified_by", "updated_at"])
                CostAudit.objects.create(
                    tenant_id=tenant_id, item=item, actor=request.user,
                    action="create", before=None, after=item.snapshot(),
                )
        except IntegrityError as exc:
            return _duplicates_response(exc)
        return Response(CostItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CostItemDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id, item_id):
        membership_or_404(request.user, tenant_id)
        item = get_object_or_404(CostItem, tenant_id=tenant_id, pk=item_id)
        return Response(CostItemSerializer(item).data)

    def patch(self, request, tenant_id, item_id):
        member = membership_or_404(request.user, tenant_id)
        if not _can_write(member):
            return Response({"detail": "Permissão somente leitura."}, status=403)
        serializer = CostWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "expected_version" not in data:
            return Response({"detail": "Envie expected_version para evitar sobrescritas."}, status=400)
        try:
            with transaction.atomic():
                item = get_object_or_404(
                    CostItem.objects.select_for_update(), tenant_id=tenant_id, pk=item_id
                )
                if item.version != data["expected_version"]:
                    return Response({"detail": "Este item mudou. Atualize a lista antes de salvar."}, status=409)
                before = item.snapshot()
                changed = False
                for key in (
                    "reference", "name", "sku", "external_variant_id",
                    "unit_cost_cents", "selling_price_cents",
                ):
                    if key in data and getattr(item, key) != data[key]:
                        if key == "unit_cost_cents":
                            item.verified_at = None
                            item.verified_by = None
                        setattr(item, key, data[key])
                        changed = True
                if data.get("verify_cost"):
                    if item.unit_cost_cents is None:
                        return Response({"detail": "Custo obrigatório para confirmação."}, status=400)
                    _mark_verified(item, data, request.user)
                    changed = True
                elif "provenance" in data and data["provenance"] != item.provenance:
                    item.provenance = data["provenance"]
                    changed = True
                if not changed:
                    return Response(CostItemSerializer(item).data)
                item.version += 1
                item.updated_by = request.user
                item.save()
                CostAudit.objects.create(
                    tenant_id=tenant_id, item=item, actor=request.user,
                    action="update", before=before, after=item.snapshot(),
                )
        except IntegrityError as exc:
            return _duplicates_response(exc)
        return Response(CostItemSerializer(item).data)


class CostHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id, item_id):
        membership_or_404(request.user, tenant_id)
        item = get_object_or_404(CostItem, tenant_id=tenant_id, pk=item_id)
        rows = item.audits.select_related("actor").order_by("-created_at")[:30]
        return Response({
            "item_id": str(item.id),
            "history": [{
                "action": row.action, "version": row.after["version"],
                "created_at": row.created_at.isoformat(),
                "by": row.actor.get_username() if row.actor else None,
                "before": row.before, "after": row.after,
            } for row in rows]
        })
