"""Situação de solicitações LGPD para o lojista, sem payload ou PII."""
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership
from .privacy_models import PrivacyWebhookRequest


class PrivacyRequestsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id):
        member = get_object_or_404(
            TenantMembership, tenant_id=tenant_id, user=request.user,
        )
        if member.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
            response=Response({"detail": "Acesso restrito a administradores."}, status=403)
        else:
            events=PrivacyWebhookRequest.objects.filter(tenant_id=tenant_id).exclude(
                state=PrivacyWebhookRequest.State.COMPLETED,
            )
            report=events.filter(
                topic=PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
            ).count()
            delete=events.exclude(
                topic=PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
            ).count()
            response=Response({
                "pending_total": report+delete,
                "access_requests": report,
                "deletion_requests": delete,
                "items": [{
                    "id": str(row.id),
                    "type": ("data_access" if row.topic ==
                             PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
                             else "deletion"),
                    "received_at": row.received_at.isoformat(),
                    "status": "em_analise",
                } for row in events.only("id","topic","received_at")[:10]],
                "note": "Pedidos recebidos são acompanhados pela Vidalys. "
                        "O registro não significa que a solicitação já foi concluída.",
            })
        response["Cache-Control"]="private, no-store"
        return response
