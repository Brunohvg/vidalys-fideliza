"""Adaptador INTERNO para pedido relido com OAuth, não para o webhook cru.

A inbox HMAC existente permanece intacta. Ela informa IDs e tópico, não
contém dados financeiros/identidade suficientes para normalizar uma venda.
A reconsulta autenticada deve fornecer o snapshot normalizado antes daqui.
"""
from django.conf import settings

from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.scopes import has_order_access
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant

from ..serializers import OrderEventSerializer
from ..services import ingest_order_event


class NuvemshopSnapshotError(ValueError):
    pass


def ingest_nuvemshop_snapshot(*, tenant_id, store_id, normalized_snapshot):
    """Sem acesso HTTP. Chamador é responsável pelo GET OAuth da loja autorizada."""
    if not settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED:
        raise NuvemshopSnapshotError("Reconsulta de pedidos desativada.")
    installation = NuvemshopInstallation.objects.filter(
        tenant_id=tenant_id, store_id=str(store_id),
        tenant__status=Tenant.Status.ACTIVE,
    ).first()
    if not installation or not has_order_access(installation.scope, preview_enabled=True):
        raise NuvemshopSnapshotError("Instalação ou escopo Nuvemshop não autorizado.")
    if not isinstance(normalized_snapshot, dict):
        raise NuvemshopSnapshotError("Snapshot deve ser um objeto normalizado.")
    serializer = OrderEventSerializer(data={
        **normalized_snapshot,
        "tenant_id": str(tenant_id),
        "channel": SaleRecord.Channel.NUVEMSHOP,
    })
    if not serializer.is_valid():
        raise NuvemshopSnapshotError("Snapshot normalizado inválido.")
    return ingest_order_event(data=serializer.validated_data)
