"""Consulta limitada à base de participantes, sem autoinscrição ou contatos importados."""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership
from .models import ProgramParticipant


class ParticipantListView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id):
        get_object_or_404(TenantMembership, tenant_id=tenant_id, user=request.user)
        allowed = {"active", "paused", "all"}
        status_filter = request.query_params.get("status", "all")
        search = request.query_params.get("q", "").strip()
        offset = request.query_params.get("offset", "0")
        if status_filter not in allowed or len(search) > 80:
            return Response({"detail": "Filtro inválido."}, status=400)
        if not offset.isascii() or not offset.isdecimal() or len(offset) > 6:
            return Response({"detail": "Paginação inválida."}, status=400)
        page_start = int(offset)
        if page_start > 50000:
            return Response({"detail": "Paginação fora do limite."}, status=400)

        # Retirada de consentimento não equivale a membro ativo.
        qs = ProgramParticipant.objects.filter(
            tenant_id=tenant_id,
            status__in=[ProgramParticipant.Status.ACTIVE, ProgramParticipant.Status.PAUSED],
        )
        summary = {
            "total": qs.count(),
            "active": qs.filter(status=ProgramParticipant.Status.ACTIVE).count(),
            "paused": qs.filter(status=ProgramParticipant.Status.PAUSED).count(),
        }
        filtered = qs
        if status_filter != "all":
            filtered = filtered.filter(status=status_filter)
        if search:
            filtered = filtered.filter(
                Q(display_name__icontains=search) |
                Q(contact_email__icontains=search) |
                Q(external_customer_id__icontains=search)
            )
        count = filtered.count()
        result = []
        for item in filtered[page_start:page_start + 20]:
            result.append({
                "id": str(item.id),
                "customer_reference": item.external_customer_id,
                "display_name": item.display_name,
                "contact_email": item.contact_email,
                "status": item.status,
                "consented_at": item.consent_at.isoformat(),
                "joined_at": item.joined_at.isoformat(),
                "last_program_activity_at": (
                    item.last_program_activity_at.isoformat()
                    if item.last_program_activity_at else None
                ),
                "consent_channel": item.consent_channel,
                # Ainda não existe carteira/ledger; não inventar saldo zero.
                "points_balance": None,
                "cashback_balance_cents": None,
                "balance_status": "not_implemented",
            })
        response = Response({
            "source": "verified_opt_in_only",
            "data_status": "no_enrollment_channel",
            "summary": summary,
            "total_filtered": count,
            "limit": 20,
            "offset": page_start,
            "items": result,
            "note": "Nenhum cliente da Nuvemshop é participante automaticamente. "
                    "A adesão só poderá ser registrada por um canal validado de aceite.",
        })
        response["Cache-Control"] = "private, no-store"
        return response
