"""Extrato privado do lojista: sem concessão ou resgate HTTP."""
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.participants.models import ProgramParticipant
from apps.tenants.models import TenantMembership
from .models import CashbackEvent, CashbackWallet
from .services import wallet_balances


class ParticipantWalletView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id, participant_id):
        get_object_or_404(TenantMembership, tenant_id=tenant_id, user=request.user)
        participant = get_object_or_404(
            ProgramParticipant,
            pk=participant_id, tenant_id=tenant_id,
            status__in=[ProgramParticipant.Status.ACTIVE, ProgramParticipant.Status.PAUSED],
        )
        wallet = CashbackWallet.objects.filter(
            tenant_id=tenant_id, participant=participant,
        ).first()
        events = []
        if wallet is not None:
            for event in CashbackEvent.objects.filter(wallet=wallet).order_by("-created_at", "-id")[:20]:
                events.append({
                    "id": str(event.id),
                    "kind": event.kind,
                    "amount_cents": event.amount_cents,
                    "rule_version": event.rule_version,
                    "created_at": event.created_at.isoformat(),
                })
        response = Response({
            "mode": "ledger_read_only",
            "balance_status": "ledger_only" if wallet else "not_implemented",
            "balances": wallet_balances(wallet),
            "events": events,
            "events_limit": 20,
            "redemption_enabled": False,
            "note": "Lançamentos internos não equivalem a cashback resgatável. "
                    "Pagamentos, liberação e checkout ainda exigem validação.",
        })
        response["Cache-Control"] = "private, no-store"
        return response
