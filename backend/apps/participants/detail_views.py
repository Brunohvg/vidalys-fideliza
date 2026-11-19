"""Página do cliente no painel: tudo sobre uma participação, e as ações do lojista.

Leitura para qualquer membro da equipe; pausar/retomar só owner/admin.
Nada aqui credita pontos, envia mensagens ou altera vendas.
"""
from django.db import transaction
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sales.campaign_engine import offers_for
from apps.sales.pilot import mode_payload
from apps.sales.policy import channels
from apps.sales.models import SaleRecord
from apps.tenants.models import TenantMembership
from .models import ProgramParticipant
from .views import participant_rows

VISIBLE = [ProgramParticipant.Status.ACTIVE, ProgramParticipant.Status.PAUSED]


def _private(data, status=200):
    response = Response(data, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


def _participant(tenant_id, participant_id, *, lock=False):
    qs = ProgramParticipant.objects.filter(tenant_id=tenant_id, status__in=VISIBLE)
    if lock:
        qs = qs.select_for_update()
    return get_object_or_404(qs, pk=participant_id)


def _detail(participant):
    tenant_id = participant.tenant_id
    row = participant_rows(tenant_id, [participant])[0]
    enrollment = getattr(participant, "local_enrollment", None)
    sales = (SaleRecord.objects.filter(tenant_id=tenant_id, participant=participant)
             .annotate(at=Coalesce("reported_paid_at", "created_at")).order_by("-at")[:25])
    return {
        "participant": row,
        "profile": {
            "email_verified": bool(enrollment and enrollment.email_verified_at),
            "marketing_opt_in": bool(enrollment and enrollment.marketing_opt_in),
            "birth_day": enrollment.birth_day if enrollment else None,
            "birth_month": enrollment.birth_month if enrollment else None,
            "terms_version": participant.terms_version,
        },
        "sales": [{
            "id": str(sale.id), "channel": sale.channel, "reference": sale.external_reference,
            "amount_cents": sale.eligible_amount_cents, "at": sale.at.isoformat() if sale.at else None,
            "state": sale.state, "order_status": sale.order_status,
        } for sale in sales],
        "offers": offers_for(tenant_id, participant.pk) if participant.status == ProgramParticipant.Status.ACTIVE else [],
        "program": mode_payload(tenant_id),
        "channels": channels(tenant_id),
    }


class ParticipantDetailView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id, participant_id):
        get_object_or_404(TenantMembership, tenant_id=tenant_id, user=request.user)
        return _private(_detail(_participant(tenant_id, participant_id)))


class ParticipantStatusView(APIView):
    """Pausar ou retomar a participação. Retirada de consentimento é do próprio cliente."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id, participant_id):
        member = get_object_or_404(TenantMembership, tenant_id=tenant_id, user=request.user)
        if member.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
            return _private({"detail": "Somente administradores podem pausar ou retomar participações."}, 403)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"status"} or data["status"] not in ("active", "paused"):
            return _private({"detail": "Informe se a participação fica ativa ou pausada."}, 400)
        participant = _participant(tenant_id, participant_id, lock=True)
        if participant.status != data["status"]:
            participant.status = data["status"]
            participant.last_program_activity_at = timezone.now()
            participant.save(update_fields=["status", "last_program_activity_at"])
        return _private({**_detail(participant), "points_credited": False, "messages_sent": False})
