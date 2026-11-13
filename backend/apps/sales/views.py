"""Entrada de venda de balcão e simulação. Nunca escreve na carteira."""
import re
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from .models import PointRuleDraft, SaleRecord
from .quote import MAX_AMOUNT_CENTS, is_int, preview_points, validate_rule

REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{3,79}$")


def safe_reply(data, status=200):
    result = Response(data, status=status)
    result["Cache-Control"] = "private, no-store"
    return result


def staff_member(user, tenant_id):
    membership = get_object_or_404(
        TenantMembership.objects.select_related("tenant"),
        user=user, tenant_id=tenant_id,
    )
    if membership.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
        return None
    return membership


def present_sale(sale, *, viewer_id=None):
    return {
        "id": str(sale.id),
        "channel": sale.channel, "reference": sale.external_reference,
        "participant_id": str(sale.participant_id) if sale.participant_id else None,
        "participant_name": sale.participant.display_name if sale.participant_id else None,
        "eligible_amount_cents": sale.eligible_amount_cents,
        "reported_paid_at": sale.reported_paid_at.isoformat(),
        "evidence_reference": sale.evidence_reference,
        "state": sale.state, "created_at": sale.created_at.isoformat(),
        "reviewed_at": sale.reviewed_at.isoformat() if sale.reviewed_at else None,
        "submitted_by_me": bool(viewer_id is not None and sale.submitted_by_id == viewer_id),
        "points_credited": False, "cashback_credited": False,
    }


class ManualSalesView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        records = SaleRecord.objects.filter(
            tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
        ).select_related("participant")[:30]
        return safe_reply({
            "mode": "manual_review_only", "points_credited": False,
            "items": [present_sale(item, viewer_id=request.user.pk) for item in records],
        })

    @transaction.atomic
    def post(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.tenant.status != Tenant.Status.ACTIVE:
            return safe_reply({"detail": "A empresa precisa estar ativa."}, 409)
        data = request.data
        expected = {"reference", "eligible_amount_cents", "participant_id",
                    "reported_paid_at", "evidence_reference"}
        if not isinstance(data, dict) or set(data) != expected:
            return safe_reply({"detail": "Informe referência, valor, participante, data e comprovante."}, 400)
        ref, amount, participant_id, raw_paid, evidence = (
            data["reference"], data["eligible_amount_cents"], data["participant_id"],
            data["reported_paid_at"], data["evidence_reference"],
        )
        if (not isinstance(ref, str) or not REFERENCE_RE.fullmatch(ref)
                or not isinstance(evidence, str) or not REFERENCE_RE.fullmatch(evidence)
                or not is_int(amount) or not 1 <= amount <= MAX_AMOUNT_CENTS
                or not isinstance(raw_paid, str)):
            return safe_reply({"detail": "Valor ou referência inválidos."}, 400)
        try:
            paid_at = parse_datetime(raw_paid)
        except (TypeError, ValueError, OverflowError):
            paid_at = None
        if (paid_at is None or timezone.is_naive(paid_at)
                or paid_at > timezone.now() + timedelta(minutes=5)
                or paid_at < timezone.now() - timedelta(days=365)):
            return safe_reply({"detail": "Data do pagamento inválida ou muito antiga."}, 400)
        participant = None
        if participant_id is not None:
            if not isinstance(participant_id, str):
                return safe_reply({"detail": "Participante inválido."}, 400)
            try:
                participant_uuid = uuid.UUID(participant_id)
            except (ValueError, TypeError, AttributeError):
                return safe_reply({"detail": "Identificador do participante inválido."}, 400)
            participant = ProgramParticipant.objects.filter(
                pk=participant_uuid, tenant_id=tenant_id,
                status=ProgramParticipant.Status.ACTIVE,
            ).first()
            if not participant:
                return safe_reply({"detail": "Participante ativo não encontrado nesta empresa."}, 409)
            if paid_at < max(participant.consent_at, participant.joined_at):
                return safe_reply({
                    "detail": "A compra é anterior à adesão confirmada. Não gera pontos.",
                }, 409)
        # Lock serializa a mesma referência, inclusive em requisições simultâneas.
        Tenant.objects.select_for_update().get(pk=tenant_id)
        previous = SaleRecord.objects.filter(
            tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
            external_reference=ref,
        ).select_related("participant").first()
        if previous:
            same = (
                previous.eligible_amount_cents == amount
                and previous.participant_id == (participant.id if participant else None)
                and previous.evidence_reference == evidence
                and previous.reported_paid_at == paid_at
            )
            if same:
                return safe_reply({"already_recorded": True, "sale": present_sale(previous, viewer_id=request.user.pk)})
            return safe_reply({"detail": "Referência já usada para outra venda."}, 409)
        sale = SaleRecord.objects.create(
            tenant_id=tenant_id, participant=participant, channel=SaleRecord.Channel.COUNTER,
            external_reference=ref, eligible_amount_cents=amount,
            reported_paid_at=paid_at, evidence_reference=evidence,
            state=(SaleRecord.State.AWAITING_REVIEW if participant
                   else SaleRecord.State.AWAITING_MEMBER),
            submitted_by=request.user,
        )
        return safe_reply({"already_recorded": False, "sale": present_sale(sale, viewer_id=request.user.pk)}, 201)


class ManualSaleReviewView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id, sale_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.tenant.status != Tenant.Status.ACTIVE:
            return safe_reply({"detail": "Empresa não está ativa."}, 409)
        if not isinstance(request.data, dict) or set(request.data) != {"decision", "note"}:
            return safe_reply({"detail": "Confirme decisão e justificativa."}, 400)
        decision, note = request.data["decision"], request.data["note"]
        if (decision not in ("approve", "reject") or not isinstance(note, str)
                or not 10 <= len(note.strip()) <= 240):
            return safe_reply({"detail": "Decisão ou justificativa inválida."}, 400)
        sale = get_object_or_404(
            SaleRecord.objects.select_for_update().select_related("participant"),
            pk=sale_id, tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
        )
        if sale.state != SaleRecord.State.AWAITING_REVIEW:
            return safe_reply({"detail": "Venda não está pendente de conferência."}, 409)
        if sale.submitted_by_id == request.user.pk:
            return safe_reply({"detail": "A conferência deve ser feita por outro administrador."}, 409)
        if not sale.participant or sale.participant.status != ProgramParticipant.Status.ACTIVE:
            return safe_reply({"detail": "Participante inativo ou ausente."}, 409)
        sale.state = (SaleRecord.State.VERIFIED_MANUAL if decision == "approve"
                      else SaleRecord.State.REJECTED)
        sale.reviewed_by = request.user
        sale.reviewed_at = timezone.now()
        sale.review_note = note.strip()
        sale.save(update_fields=["state", "reviewed_by", "reviewed_at", "review_note"])
        # Revisão operacional != pagamento confirmado por PSP. Sem saldo.
        return safe_reply({
            "sale": present_sale(sale, viewer_id=request.user.pk),
            "manual_evidence_reviewed": True,
            "independent_payment_proof": False,
            "points_credited": False,
        })


class PointRuleDraftView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        rule = PointRuleDraft.objects.filter(tenant_id=tenant_id).first()
        return safe_reply({
            "mode": "draft_only", "activation_available": False,
            "rule": ({
                "version": rule.version,
                "points": rule.points, "per_cents": rule.per_cents,
                "hold_days": rule.hold_days, "validity_days": rule.validity_days,
            } if rule else None),
        })

    @transaction.atomic
    def post(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.tenant.status != Tenant.Status.ACTIVE:
            return safe_reply({"detail": "Empresa não está ativa."}, 409)
        try:
            data = validate_rule(request.data)
        except ValueError as exc:
            return safe_reply({"detail": str(exc)}, 400)
        Tenant.objects.select_for_update().get(pk=tenant_id)
        rule = PointRuleDraft.objects.filter(tenant_id=tenant_id).first()
        if rule:
            changed = any(getattr(rule, field) != value for field, value in data.items())
            if changed:
                for field, value in data.items():
                    setattr(rule, field, value)
                rule.version += 1
                rule.updated_by = request.user
                rule.save()
        else:
            rule = PointRuleDraft.objects.create(tenant_id=tenant_id, updated_by=request.user, **data)
        return safe_reply({
            "mode": "draft_only", "activation_available": False,
            "version": rule.version, "points": rule.points,
            "per_cents": rule.per_cents, "hold_days": rule.hold_days,
            "validity_days": rule.validity_days,
            "example_for_100_reais": preview_points(
                eligible_amount_cents=10000, points=rule.points, per_cents=rule.per_cents,
            ),
            "points_credited": False,
        })
