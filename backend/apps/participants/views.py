"""Consulta limitada à base de participantes, sem autoinscrição ou contatos importados."""
from django.db.models import Q, Sum, Count, Max
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership
from .models import ProgramParticipant
from apps.wallets.services import balances_for_participants
from apps.points.models import PointWallet, PointEntry
from apps.sales.models import SaleRecord


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
        page = list(filtered[page_start:page_start + 20])
        balances = balances_for_participants(
            tenant_id=tenant_id, participant_ids=[item.id for item in page],
        )
        # Uma agregação por página evita N+1 e nunca soma cashback em BRL.
        participant_ids = [item.id for item in page]
        point_wallets = set(PointWallet.objects.filter(
            tenant_id=tenant_id,participant_id__in=participant_ids,
        ).values_list("participant_id",flat=True))
        point_balances = {
            pid:{"pending":0,"available":0,"reserved":0} for pid in point_wallets
        }
        point_rows = PointEntry.objects.filter(
            event__lot__wallet__tenant_id=tenant_id,
            event__lot__tenant_id=tenant_id,
            event__lot__wallet__participant_id__in=participant_ids,
            event__lot__expires_at__gt=timezone.now(),
        ).values("event__lot__wallet__participant_id","bucket").annotate(total=Sum("delta"))
        for row in point_rows:
            pid = row["event__lot__wallet__participant_id"]
            if pid in point_balances:
                point_balances[pid][row["bucket"]] = row["total"] or 0
        # Agregação por participante, apenas do balcão desta loja. Esses
        # valores são informados no caixa, NÃO receita confirmada pelo PSP.
        manual_summary = {}
        sales_rows = (SaleRecord.objects.filter(
            tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
            participant_id__in=participant_ids,
        ).values("participant_id").annotate(
            manual_sales_count=Count("id"),
            manual_sales_reviewed=Count("id", filter=Q(state=SaleRecord.State.VERIFIED_MANUAL)),
            manual_sales_pending=Count("id", filter=Q(state=SaleRecord.State.AWAITING_REVIEW)),
            manual_sales_reported_cents=Sum("eligible_amount_cents"),
            last_manual_sale_at=Max("reported_paid_at"),
        ))
        for row in sales_rows:
            manual_summary[row["participant_id"]] = row
        result = []
        for item in page:
            wallet_balance = balances.get(item.id)
            point = point_balances.get(item.id)
            manual = manual_summary.get(item.id)
            if point and any(v < 0 for v in point.values()):
                point = None
            result.append({
                "id": str(item.id),
                "customer_reference": item.external_customer_id,
                "nuvemshop_customer_linked": bool(item.external_customer_id),
                "manual_sales_count": manual["manual_sales_count"] if manual else 0,
                "manual_sales_reviewed": manual["manual_sales_reviewed"] if manual else 0,
                "manual_sales_pending": manual["manual_sales_pending"] if manual else 0,
                "manual_sales_reported_cents": manual["manual_sales_reported_cents"] if manual else 0,
                "last_manual_sale_at": (
                    manual["last_manual_sale_at"].isoformat() if manual and manual["last_manual_sale_at"]
                    else None
                ),
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
                # Ledger interno não implica cashback resgatável.
                "points_balance": point["available"] if point else None,
                "points_pending": point["pending"] if point else None,
                "points_status": "ledger_only" if point is not None else "not_active",
                "cashback_balance_cents": (
                    wallet_balance["available_cents"] if wallet_balance else None
                ),
                "cashback_pending_cents": (
                    wallet_balance["pending_cents"] if wallet_balance else None
                ),
                "cashback_reserved_cents": (
                    wallet_balance["reserved_cents"] if wallet_balance else None
                ),
                "balance_status": "ledger_only" if wallet_balance else "not_implemented",
            })
        response = Response({
            "source": "verified_opt_in_only",
            "data_status": "consent_verified" if summary["total"] else "no_enrollment_channel",
            "summary": summary,
            "total_filtered": count,
            "limit": 20,
            "offset": page_start,
            "items": result,
            "note": "Somente participantes com adesão expressa e e-mail confirmado. "
                    "A ligação com plataformas externas é opcional e não ativa recompensas.",
        })
        response["Cache-Control"] = "private, no-store"
        return response
