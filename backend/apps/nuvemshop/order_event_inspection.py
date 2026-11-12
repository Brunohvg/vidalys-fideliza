"""Conferência de evento da inbox contra a API atual da loja.

Este GET reutiliza permissões, rate-limit e validações da prévia.
Nenhum webhook representa por si uma confirmação financeira.
"""
from django.conf import settings
from django.shortcuts import get_object_or_404
from apps.tenants.models import TenantMembership
from .order_preview_views import OrderPreviewView
from .order_webhook_models import OrderWebhookEvent
from .views import member_for


class OrderEventInspectionView(OrderPreviewView):
    """Confere o estado atual do pedido notificado sem alterar o banco."""

    def get(self, request, tenant_id, event_id):
        member = member_for(request.user, tenant_id)
        if member.role not in (
            TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN,
        ):
            return self.answer({"detail": "Acesso restrito à administração."}, 403)
        if not settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED:
            return self.answer({"detail": "Eventos de pedidos desativados."}, 409)
        event = get_object_or_404(
            OrderWebhookEvent, pk=event_id, tenant_id=tenant_id,
        )
        result = super().get(request, tenant_id, int(event.order_id))
        if result.status_code == 200:
            result.data["event_receipt"] = {
                "id": str(event.id), "topic": event.topic,
                "received_at": event.received_at.isoformat(),
            }
            result.data["inspection_mode"] = "current_order_snapshot_only"
            result.data["event_proves_payment"] = False
            result.data["requires_psp_reconciliation"] = True
        return result
