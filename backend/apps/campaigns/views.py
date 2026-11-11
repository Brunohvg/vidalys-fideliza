"""Rascunhos simples; nunca concedem crédito, publicam cupom ou enviam mensagens."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership
from .models import CampaignDraft
from .serializers import CampaignDraftSerializer, WRITABLE_FIELDS


MAX_DRAFTS_PER_TENANT = 30


def membership_for(request, tenant_id):
    return get_object_or_404(TenantMembership, tenant_id=tenant_id, user=request.user)


def allowed_to_edit(membership):
    return membership.role in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


def private(response):
    response["Cache-Control"] = "private, no-store"
    return response


class CampaignDraftListView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        membership_for(request, tenant_id)
        drafts = CampaignDraft.objects.filter(tenant_id=tenant_id)[:MAX_DRAFTS_PER_TENANT]
        return private(Response({
            "mode": "draft_only",
            "activation_available": False,
            "items": CampaignDraftSerializer(drafts, many=True).data,
        }))

    @transaction.atomic
    def post(self, request, tenant_id):
        membership = membership_for(request, tenant_id)
        if not allowed_to_edit(membership):
            return private(Response({"detail": "Apenas proprietário ou administrador pode salvar."}, status=403))
        if not isinstance(request.data, dict) or set(request.data) != WRITABLE_FIELDS:
            return private(Response({"detail": "Envie somente os seis campos de planejamento."}, status=400))
        # Lock de tenant impede duas gravações simultâneas de ultrapassar o limite.
        from apps.tenants.models import Tenant
        Tenant.objects.select_for_update().get(pk=tenant_id)
        if CampaignDraft.objects.filter(tenant_id=tenant_id).count() >= MAX_DRAFTS_PER_TENANT:
            return private(Response({"detail": "Limite de 30 rascunhos por loja atingido."}, status=409))
        serializer = CampaignDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(
            tenant_id=tenant_id, created_by=request.user, updated_by=request.user,
        )
        return private(Response(CampaignDraftSerializer(item).data, status=201))


class CampaignDraftDetailView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request, tenant_id, draft_id):
        membership_for(request, tenant_id)
        item = get_object_or_404(CampaignDraft, pk=draft_id, tenant_id=tenant_id)
        return private(Response(CampaignDraftSerializer(item).data))

    @transaction.atomic
    def patch(self, request, tenant_id, draft_id):
        membership = membership_for(request, tenant_id)
        if not allowed_to_edit(membership):
            return private(Response({"detail": "Você não tem permissão para alterar rascunhos."}, status=403))
        if (not isinstance(request.data, dict)
                or set(request.data) != WRITABLE_FIELDS | {"expected_version"}):
            return private(Response({"detail": "Revise os campos e a versão esperada."}, status=400))
        item = get_object_or_404(
            CampaignDraft.objects.select_for_update(),
            pk=draft_id, tenant_id=tenant_id,
        )
        expected = request.data["expected_version"]
        if type(expected) is not int or expected != item.version:
            return private(Response({
                "detail": "Rascunho alterado em outra sessão. Atualize antes de salvar.",
                "current_version": item.version,
            }, status=409))
        serializer = CampaignDraftSerializer(
            item, data={field: request.data[field] for field in WRITABLE_FIELDS},
            partial=False,
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.save(updated_by=request.user, version=item.version + 1)
        return private(Response(CampaignDraftSerializer(item).data))
