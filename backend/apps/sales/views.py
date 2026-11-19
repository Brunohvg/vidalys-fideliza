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


def suggested_participants(sales):
    """Vendas sem cliente cujo celular agora pertence a um participante ativo."""
    digests = {s.counter_phone_digest for s in sales
               if s.state == SaleRecord.State.AWAITING_MEMBER and s.counter_phone_digest}
    if not digests:
        return {}
    tenant_ids = {s.tenant_id for s in sales}
    found = ProgramParticipant.objects.filter(
        tenant_id__in=tenant_ids, phone_digest__in=digests,
        status=ProgramParticipant.Status.ACTIVE,
    )
    return {(p.tenant_id, p.phone_digest): p for p in found}


def present_sale(sale, *, viewer_id=None, suggestions=None, pilot=False, avg_ticket=0):
    hint = None
    if (suggestions and sale.state == SaleRecord.State.AWAITING_MEMBER
            and sale.counter_phone_digest):
        match = suggestions.get((sale.tenant_id, sale.counter_phone_digest))
        if match:
            hint = {"id": str(match.id), "display_name": match.display_name,
                    "phone_last4": match.phone_last4 or None}
    return {
        "suggested_participant": hint,
        "id": str(sale.id),
        "channel": sale.channel, "reference": sale.external_reference,
        "participant_id": str(sale.participant_id) if sale.participant_id else None,
        "participant_name": sale.participant.display_name if sale.participant_id else None,
        "eligible_amount_cents": sale.eligible_amount_cents,
        "reported_paid_at": sale.reported_paid_at.isoformat() if sale.reported_paid_at else None,
        "evidence_reference": sale.evidence_reference,
        "state": sale.state, "created_at": sale.created_at.isoformat(),
        "reviewed_at": sale.reviewed_at.isoformat() if sale.reviewed_at else None,
        "submitted_by_me": bool(viewer_id is not None and sale.submitted_by_id == viewer_id),
        "reviewed_by_me": bool(viewer_id is not None and sale.reviewed_by_id == viewer_id),
        "review_mode": (
            "self_review" if sale.reviewed_by_id and sale.reviewed_by_id == sale.submitted_by_id
            else "another_operator" if sale.reviewed_by_id else None
        ),
        "review_note": sale.review_note if sale.reviewed_at else None,
        "points_credited": False, "cashback_credited": False,
        **(pilot_view(sale, viewer_id, avg_ticket) if pilot else {}),
    }


def pilot_view(sale, viewer_id, avg_ticket):
    """Campos do piloto: pontos, vale, alertas e se ainda dá para desfazer."""
    from .pilot import can_undo, points_for, sale_alerts, sale_lot
    redemption = getattr(sale, "counter_redemption", None)
    discount = redemption.discount_cents if redemption and redemption.state != "cancelled" else 0
    lot = sale_lot(sale) if sale.state == SaleRecord.State.VERIFIED_MANUAL else None
    preview, capped = points_for(sale.tenant_id, sale.eligible_amount_cents - discount)
    return {
        "points_issued": lot.points_issued if lot else None,
        "points_unlock_at": lot.unlock_at.isoformat() if lot else None,
        "points_preview": preview, "points_capped": capped,
        "redemption": ({"title": redemption.reward.title if redemption.reward_id else "Crédito de giftback",
                        "points": redemption.points,
                        "discount_cents": redemption.discount_cents, "state": redemption.state}
                       if redemption else None),
        "alerts": sale_alerts(sale, avg_ticket) if sale.state == SaleRecord.State.AWAITING_REVIEW else [],
        "can_undo": can_undo(sale, viewer_id),
        "submitted_by_name": (sale.submitted_by.get_username() if sale.submitted_by_id else None),
    }


class ManualSalesView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        from .pilot import average_ticket, mode_payload, pilot_enabled
        records = list(SaleRecord.objects.filter(
            tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
        ).select_related("participant", "submitted_by", "counter_redemption__reward")[:60])
        hints = suggested_participants(records)
        pilot = pilot_enabled(tenant_id)
        avg = average_ticket(tenant_id)
        return safe_reply({
            "mode": "pilot_points" if pilot else "manual_review_only", "points_credited": False,
            "pilot_active": pilot, "average_ticket_cents": avg, "program": mode_payload(tenant_id),
            "items": [present_sale(item, viewer_id=request.user.pk, suggestions=hints, pilot=True, avg_ticket=avg)
                      for item in records],
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
        if not isinstance(data, dict) or not expected <= set(data) <= expected | {"customer_phone", "reward_id", "use_credit"}:
            return safe_reply({"detail": "Informe referência, valor, participante, data e comprovante."}, 400)
        use_credit = data.get("use_credit", False)
        if type(use_credit) is not bool or (use_credit and data.get("participant_id") is None):
            return safe_reply({"detail": "Crédito só pode ser usado por cliente do clube."}, 400)
        if use_credit and data.get("reward_id") is not None:
            return safe_reply({"detail": "Use o crédito ou um vale, não os dois."}, 400)
        reward_id = data.get("reward_id")
        if reward_id is not None:
            try:
                reward_id = uuid.UUID(str(reward_id))
            except (ValueError, TypeError):
                return safe_reply({"detail": "Vale inválido."}, 400)
            if data.get("participant_id") is None:
                return safe_reply({"detail": "Vale só pode ser usado por cliente do clube."}, 400)
        # Celular de quem ainda não participa: guarda só o HMAC para vincular depois.
        phone_digest = ""
        raw_phone = data.get("customer_phone", "")
        if raw_phone not in ("", None):
            from apps.participants.phone import phone_fields
            try:
                phone_digest, _last4 = phone_fields(tenant_id=tenant_id, raw=raw_phone)
            except ValueError as exc:
                return safe_reply({"detail": str(exc)}, 400)
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
        # Único pipeline para vendas de balcão e Flow. A entrada humana não
        # comprova captura nem cria saldo; revisão continua operacional.
        from apps.channels.services import ingest_order_event, IngestionConflict
        try:
            outcome = ingest_order_event(
                data={
                    "tenant_id": member.tenant.pk,
                    "channel": SaleRecord.Channel.COUNTER,
                    "external_order_id": ref,
                    "customer_identifier": f"manual:{participant.pk}" if participant else "",
                    "total_amount": amount,
                    "currency": "BRL",
                    "status": SaleRecord.OrderStatus.PAID,
                    "source_event_id": "",
                    "occurred_at": paid_at,
                },
                actor=request.user,
                manual_override={
                    "participant": participant, "evidence_reference": evidence,
                },
            )
        except IngestionConflict:
            return safe_reply({"detail": "Evento incompatível com uma venda já registrada."}, 409)
        sale = outcome.sale
        if (reward_id is not None or use_credit) and not outcome.duplicate:
            from .pilot import PilotBlocked, reserve_credit, reserve_reward
            try:
                with transaction.atomic():
                    if use_credit:
                        reserve_credit(sale=sale, participant=participant, operator=request.user)
                    else:
                        reserve_reward(sale=sale, participant=participant, reward_id=reward_id, operator=request.user)
            except (PilotBlocked, ValueError, PermissionError) as exc:
                transaction.set_rollback(True)
                return safe_reply({"detail": str(exc)}, 409)
        if (phone_digest and not outcome.duplicate and sale.participant_id is None
                and sale.state == SaleRecord.State.AWAITING_MEMBER and not sale.counter_phone_digest):
            sale.counter_phone_digest = phone_digest
            sale.save(update_fields=["counter_phone_digest"])
        return safe_reply({
            "already_recorded": outcome.duplicate,
            "sale": present_sale(outcome.sale, viewer_id=request.user.pk, pilot=True),
            "event_id": str(outcome.event.pk),
            "identity_status": outcome.identity_status,
            "payment_verified": False, "points_credited": False,
        }, 200 if outcome.duplicate else 201)


class ManualSaleLinkView(APIView):
    """Conecta venda sem CPF/telefone inicial somente ao perfil com OTP comprovado."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id, sale_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.tenant.status != Tenant.Status.ACTIVE:
            return safe_reply({"detail": "Loja inativa."}, 409)
        if not isinstance(request.data, dict) or set(request.data) != {"participant_id"}:
            return safe_reply({"detail": "Informe o participante confirmado."}, 400)
        try:
            participant_id = uuid.UUID(request.data["participant_id"])
        except (ValueError, TypeError, AttributeError, KeyError):
            return safe_reply({"detail": "Identificador de participante inválido."}, 400)
        from .services import attach_verified_counter_sale, ManualLinkBlocked
        try:
            sale = attach_verified_counter_sale(
                tenant_id=tenant_id, sale_id=sale_id,
                participant_id=participant_id, operator=request.user,
            )
        except (ManualLinkBlocked, SaleRecord.DoesNotExist, ProgramParticipant.DoesNotExist):
            return safe_reply({"detail": "Venda ou identidade ainda não pode ser vinculada."}, 409)
        return safe_reply({
            "sale": present_sale(sale, viewer_id=request.user.pk),
            "identity_status": "verified_contact_match",
            "payment_verified": False, "points_credited": False,
        })


def review_sale(sale, user, decision, note):
    """Aprova ou recusa uma venda pendente (trava já obtida). No piloto, aprovar gera pontos."""
    from .pilot import grant_for_review, settle_redemption
    sale.state = (SaleRecord.State.VERIFIED_MANUAL if decision == "approve"
                  else SaleRecord.State.REJECTED)
    sale.reviewed_by = user
    sale.reviewed_at = timezone.now()
    sale.review_note = note.strip()
    sale.save(update_fields=["state", "reviewed_by", "reviewed_at", "review_note"])
    settle_redemption(sale, approve=decision == "approve")
    points, reason = (grant_for_review(sale, user) if decision == "approve" else (0, "rejected"))
    return points, reason


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
        Tenant.objects.select_for_update().get(pk=tenant_id)
        sale = get_object_or_404(
            SaleRecord.objects.select_for_update().select_related("participant"),
            pk=sale_id, tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
        )
        if sale.state != SaleRecord.State.AWAITING_REVIEW:
            return safe_reply({"detail": "Venda não está pendente de conferência."}, 409)
        # Revisão operacional pode ser feita pelo próprio responsável quando
        # a loja trabalha com uma única pessoa. Nunca vira prova PSP.
        self_review = sale.submitted_by_id == request.user.pk
        if not sale.participant or sale.participant.status != ProgramParticipant.Status.ACTIVE:
            return safe_reply({"detail": "Participante inativo ou ausente."}, 409)
        points, reason = review_sale(sale, request.user, decision, note)
        # Fora do piloto: revisão operacional != pagamento confirmado por PSP. Sem saldo.
        return safe_reply({
            "sale": present_sale(sale, viewer_id=request.user.pk, pilot=True),
            "manual_evidence_reviewed": True,
            "review_mode": "self_review" if self_review else "another_operator",
            "independent_payment_proof": False,
            "points_credited": points > 0, "points": points, "points_reason": reason,
        })


class ManualSaleBatchConfirmView(APIView):
    """Confirma de uma vez as vendas pendentes SEM alerta. As com alerta ficam para conferir uma a uma."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.tenant.status != Tenant.Status.ACTIVE:
            return safe_reply({"detail": "Empresa não está ativa."}, 409)
        ids = request.data.get("ids") if isinstance(request.data, dict) and set(request.data) == {"ids"} else None
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50:
            return safe_reply({"detail": "Informe de 1 a 50 vendas."}, 400)
        try:
            ids = [uuid.UUID(str(value)) for value in ids]
        except (ValueError, TypeError):
            return safe_reply({"detail": "Venda inválida."}, 400)
        from .pilot import average_ticket, sale_alerts
        Tenant.objects.select_for_update().get(pk=tenant_id)
        avg = average_ticket(tenant_id)
        sales = SaleRecord.objects.select_for_update().select_related("participant").filter(
            tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER, pk__in=ids,
            state=SaleRecord.State.AWAITING_REVIEW,
        ).order_by("created_at")
        confirmed, skipped, total_points = [], [], 0
        for sale in sales:
            active = sale.participant and sale.participant.status == ProgramParticipant.Status.ACTIVE
            if not active or sale_alerts(sale, avg):
                skipped.append(str(sale.pk))
                continue
            points, _reason = review_sale(sale, request.user, "approve", "Conferida em lote pelo lojista no painel.")
            total_points += points
            confirmed.append(str(sale.pk))
        return safe_reply({"confirmed": confirmed, "skipped": skipped, "points": total_points})


class ManualSaleUndoView(APIView):
    """Quem registrou desfaz em até 5 minutos, antes da conferência. Vale volta ao saldo."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id, sale_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        from .pilot import can_undo, settle_redemption
        sale = get_object_or_404(SaleRecord.objects.select_for_update(),
                                 pk=sale_id, tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER)
        if not can_undo(sale, request.user.pk):
            return safe_reply({"detail": "Só quem registrou desfaz, em até 5 minutos e antes da conferência."}, 409)
        sale.state = SaleRecord.State.REJECTED
        sale.reviewed_by = request.user
        sale.reviewed_at = timezone.now()
        sale.review_note = "Desfeita por quem registrou."
        sale.save(update_fields=["state", "reviewed_by", "reviewed_at", "review_note"])
        settle_redemption(sale, approve=False)
        return safe_reply({"sale": present_sale(sale, viewer_id=request.user.pk, pilot=True)})


class CounterWalletView(APIView):
    """Saldo e vales da cliente para o vendedor, na hora da venda."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id, participant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        from .pilot import counter_wallet
        participant = get_object_or_404(ProgramParticipant, pk=participant_id, tenant_id=tenant_id,
                                        status=ProgramParticipant.Status.ACTIVE)
        return safe_reply(counter_wallet(participant))


class CounterPilotView(APIView):
    """Liga, pausa e ajusta os tetos do piloto. Só o proprietário."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        from .pilot import pilot_state
        return safe_reply(pilot_state(member.tenant))

    @transaction.atomic
    def post(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.role != TenantMembership.Role.OWNER:
            return safe_reply({"detail": "Somente o proprietário liga ou pausa o piloto."}, 403)
        from .models import CounterPilot
        from .pilot import pilot_allowed, pilot_state
        data = request.data
        site_keys = {"online_earning", "online_coupons", "coupon_combines", "coupons_paused"}
        allowed_keys = {"active", "per_sale_cap_points", "budget_points", *site_keys}
        if not isinstance(data, dict) or not data or not set(data) <= allowed_keys:
            return safe_reply({"detail": "Informe se o piloto fica ativo e os tetos."}, 400)
        for key in ("active", *site_keys):
            if key in data and type(data[key]) is not bool:
                return safe_reply({"detail": "Opção deve ser sim ou não."}, 400)
        for key, top in (("per_sale_cap_points", 100_000), ("budget_points", 10_000_000)):
            if key in data and not (is_int(data[key]) and 1 <= data[key] <= top):
                return safe_reply({"detail": "Teto fora dos limites."}, 400)
        tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
        if data.get("active") and not pilot_allowed(tenant):
            return safe_reply({"detail": "O piloto não está liberado para esta loja neste servidor."}, 409)
        from .pilot import program_mode
        if (data.get("active") and not program_mode(tenant.pk)
                and not PointRuleDraft.objects.filter(tenant=tenant).exists()):
            return safe_reply({"detail": "Salve a regra de pontos antes de ativar o piloto."}, 409)
        pilot, _ = CounterPilot.objects.get_or_create(tenant=tenant, defaults={"updated_by": request.user})
        now = timezone.now()
        for key in ("per_sale_cap_points", "budget_points", *site_keys):
            if key in data:
                setattr(pilot, key, data[key])
        if "active" in data and data["active"] != pilot.active:
            pilot.active = data["active"]
            if pilot.active:
                pilot.activated_at, pilot.paused_at = now, None
            else:
                pilot.paused_at = now
        pilot.updated_by = request.user
        pilot.save()
        return safe_reply(pilot_state(tenant))


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


GIFTBACK_LIMITS = {
    "giftback_bps": (100, 3000), "giftback_cap_cents": (100, 100_000),
    "giftback_min_order_cents": (0, 1_000_000), "giftback_validity_days": (7, 365),
    "giftback_hold_days": (0, 30),
}


def present_mode(tenant):
    from .models import ProgramMode
    row = ProgramMode.objects.filter(tenant=tenant).first()
    defaults = ProgramMode(tenant=tenant)
    source = row or defaults
    return {
        "mode": source.mode, "saved": row is not None,
        **{key: getattr(source, key) for key in GIFTBACK_LIMITS},
    }


class ProgramModeView(APIView):
    """Pontos ou giftback: um modo por loja. Trocar não apaga saldos já emitidos."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        from .pilot import average_ticket
        return safe_reply({**present_mode(member.tenant), "average_ticket_cents": average_ticket(tenant_id)})

    @transaction.atomic
    def post(self, request, tenant_id):
        member = staff_member(request.user, tenant_id)
        if not member:
            return safe_reply({"detail": "Acesso restrito à administração."}, 403)
        if member.tenant.status != Tenant.Status.ACTIVE:
            return safe_reply({"detail": "Empresa não está ativa."}, 409)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"mode", *GIFTBACK_LIMITS}:
            return safe_reply({"detail": "Informe o modo e todos os campos do giftback."}, 400)
        if data["mode"] not in ("points", "giftback"):
            return safe_reply({"detail": "Modo inválido."}, 400)
        for key, (low, high) in GIFTBACK_LIMITS.items():
            if not (is_int(data[key]) and low <= data[key] <= high):
                return safe_reply({"detail": "Valor fora dos limites recomendados."}, 400)
        if data["giftback_min_order_cents"] <= data["giftback_cap_cents"]:
            return safe_reply({"detail": "O pedido mínimo precisa ser maior que o teto do crédito."}, 400)
        from .models import ProgramMode
        tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
        row = ProgramMode.objects.filter(tenant=tenant).first()
        if row is None:
            row = ProgramMode(tenant=tenant, updated_by=request.user)
        elif any(getattr(row, key) != data[key] for key in ("mode", *GIFTBACK_LIMITS)):
            row.version += 1
        row.mode = data["mode"]
        for key in GIFTBACK_LIMITS:
            setattr(row, key, data[key])
        row.updated_by = request.user
        row.save()
        return safe_reply({**present_mode(tenant), "points_credited": False})


class ClubResultsView(APIView):
    """Resultado do clube no período (30 ou 90 dias). Leitura para a equipe da loja."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id):
        member = TenantMembership.objects.filter(tenant_id=tenant_id, user=request.user).select_related("tenant").first()
        if member is None:
            return safe_reply({"detail": "Loja não encontrada."}, 404)
        days = request.query_params.get("days", "30")
        if days not in ("30", "90"):
            return safe_reply({"detail": "Período inválido."}, 400)
        from .results import club_results
        return safe_reply(club_results(member.tenant, days=int(days)))
