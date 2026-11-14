"""HTTP mínimo e seguro: o serviço faz TODAS as alterações de domínio."""
from django.db import IntegrityError
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from apps.tenants.models import TenantMembership

from .serializers import OrderEventSerializer
from .services import IngestionConflict, authenticate_flow_key, ingest_order_event


class OrderEventIngestView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "orders_ingest"
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = OrderEventSerializer(data=request.data)
        if not serializer.is_valid():
            return self._answer(serializer.errors, 400)
        data = serializer.validated_data
        channel = data["channel"]
        actor = None
        if channel == SaleRecord.Channel.VIDALYS_FLOW:
            credential = authenticate_flow_key(
                tenant_id=data["tenant_id"],
                authorization=request.headers.get("Authorization", ""),
            )
            if credential is None:
                return self._answer({"detail": "Credencial de integração inválida."}, 401)
        elif channel == SaleRecord.Channel.COUNTER:
            if not request.user or not request.user.is_authenticated:
                return self._answer({"detail": "Autenticação do lojista obrigatória."}, 401)
            if not TenantMembership.objects.filter(
                tenant_id=data["tenant_id"], user=request.user,
                role__in=(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN),
                tenant__status="active",
            ).exists():
                return self._answer({"detail": "Acesso negado para esta loja."}, 403)
            actor = request.user
        else:
            # Nuvemshop somente via adaptador servidor e OAuth; não aceitar
            # payload externo que finja ser webhook ou um pedido pago.
            return self._answer({"detail": "Canal exige adaptador autenticado."}, 403)
        try:
            result = ingest_order_event(data=data, actor=actor)
        except IngestionConflict as exc:
            return self._answer({"detail": str(exc)}, 409)
        except (ValueError, IntegrityError):
            return self._answer({"detail": "Evento inválido ou concorrente. Consulte o estado atual."}, 409)
        except Tenant.DoesNotExist:
            return self._answer({"detail": "Loja indisponível."}, 404)
        return self._answer({
            "sale_id": str(result.sale.pk),
            "event_id": str(result.event.pk),
            "channel": result.sale.channel,
            "external_order_id": result.sale.external_reference,
            "order_status": result.sale.order_status,
            "event_outcome": result.event.outcome,
            "identity_status": result.identity_status,
            "loyalty_readiness": result.loyalty_readiness,
            "created": result.created,
            "duplicate": result.duplicate,
            "payment_verified": False,
            "points_credited": False,
            "cashback_credited": False,
        }, 201 if result.created else 200)

    @staticmethod
    def _answer(data, status=200):
        result = Response(data, status=status)
        result["Cache-Control"] = "private, no-store"
        return result
