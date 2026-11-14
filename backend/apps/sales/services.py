"""Vinculação tardia do balcão sob identidade comprovada, sem concessão."""
from django.db import transaction

from apps.customers.models import CustomerProfile
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant

from .models import SaleManualLinkAudit, SaleRecord


class ManualLinkBlocked(ValueError):
    pass


@transaction.atomic
def attach_verified_counter_sale(*, tenant_id, sale_id, participant_id, operator):
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id, status=Tenant.Status.ACTIVE)
    sale = SaleRecord.objects.select_for_update().get(pk=sale_id, tenant=tenant)
    if sale.channel != SaleRecord.Channel.COUNTER:
        raise ManualLinkBlocked("Somente vendas de balcão podem usar este vínculo.")
    if sale.participant_id is not None or sale.state != SaleRecord.State.AWAITING_MEMBER:
        raise ManualLinkBlocked("Venda já vinculada ou fora da etapa de identificação.")
    participant = ProgramParticipant.objects.get(
        pk=participant_id, tenant=tenant, status=ProgramParticipant.Status.ACTIVE,
    )
    profile = CustomerProfile.objects.filter(
        tenant=tenant, participant=participant,
        verified_contacts__isnull=False,
    ).distinct().first()
    if profile is None:
        raise ManualLinkBlocked("Participante precisa confirmar um contato antes do vínculo.")
    sale.customer_profile = profile
    sale.participant = participant
    sale.state = SaleRecord.State.AWAITING_REVIEW
    sale.save(update_fields=["customer_profile", "participant", "state"])
    SaleManualLinkAudit.objects.create(
        tenant=tenant, sale=sale, participant=participant,
        profile=profile, linked_by=operator,
    )
    # Nunca altera captura PSP, source_order_key, ledger ou elegibilidade.
    return sale
