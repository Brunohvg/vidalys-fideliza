from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership

from .serializers import MarginSimulationSerializer
from .services import simulate_margin


class TenantMarginSimulationView(APIView):
    """Cálculo somente-leitura, autenticado e isolado por loja.

    Mesmo sendo um POST para transmitir dados, não salva nada, não oferece
    benefício e não altera pedidos ou produtos.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_id):
        if not TenantMembership.objects.filter(
            tenant_id=tenant_id, user=request.user
        ).exists():
            raise Http404

        serializer = MarginSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(simulate_margin(serializer.validated_data))
