from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership

from .planning import plan_campaign
from .planning_serializers import CampaignPlanningSerializer


class CampaignPlanPreviewView(APIView):
    """Prévia autenticada, sem persistência, isolada por loja."""

    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_id):
        if not TenantMembership.objects.filter(
            tenant_id=tenant_id, user=request.user
        ).exists():
            raise Http404

        serializer = CampaignPlanningSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(plan_campaign(serializer.validated_data))
