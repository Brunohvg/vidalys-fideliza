from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import TenantMembership

class MyTenantsView(APIView):
    """Somente lojas associadas ao usuário autenticado."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = TenantMembership.objects.filter(
            user=request.user
        ).select_related("tenant").order_by("tenant__name")
        return Response({"results": [{
            "id": str(member.tenant_id),
            "name": member.tenant.name,
            "status": member.tenant.status,
            "role": member.role,
        } for member in memberships]})
