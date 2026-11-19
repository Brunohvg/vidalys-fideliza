"""Remover cliente do clube a pedido da loja (LGPD, erro de cadastro, pedido da cliente).

O que acontece, nesta ordem e com tudo registrado:
1. cupons do site ainda válidos são apagados na Nuvemshop (se não der agora, nada muda e a loja
   tenta de novo: não removemos ninguém deixando cupom vivo);
2. o saldo que ela tinha é zerado no ledger (reserva devolvida, pendente e disponível estornados).
   O ledger nunca apaga lançamentos: o histórico fica, sem dados pessoais;
3. os dados pessoais são apagados (nome, e-mail, celular, aniversário, vínculo com a Nuvemshop)
   e a participação fica "encerrada"; ela some das listas.
Vendas e pedidos antigos continuam nos números da loja, ligados a "Cliente removido".
"""
import hashlib
import logging

from django.db import transaction
from django.utils import timezone

from .models import ProgramParticipant

logger = logging.getLogger(__name__)
REMOVED_NAME = "Cliente removido"


class RemovalBlocked(RuntimeError):
    pass


def _anonymous_email(participant):
    tag = hashlib.sha256(f"removed|{participant.pk}".encode()).hexdigest()[:16]
    return f"removido-{tag}@removido.invalid"


def remove_participant(participant, *, actor, reason=""):
    from apps.points.models import PointEvent, PointWallet
    from apps.points.services import lot_balances, transition_points
    from apps.sales.models import CounterRedemption, OnlineCoupon
    from apps.sales.online import ACTIVE, revoke_coupon
    from apps.sales.pilot import _live_lots, settle_redemption
    from .enrollment_models import EnrollmentCustomerLink, EnrollmentEmailChallenge, EnrollmentSubmission

    # 1) Cupons do site, ANTES e fora da transação principal (fala com a Nuvemshop). Cada
    #    cancelamento é completo e consistente sozinho (cupom apagado lá + reserva devolvida aqui).
    #    Se a remoção falhar depois, a cliente fica como estava, só que sem cupom: rodar de novo
    #    conclui. Nunca removemos alguém deixando cupom vivo.
    coupons_cancelled = 0
    for coupon in OnlineCoupon.objects.filter(participant=participant, state__in=ACTIVE):
        try:
            revoke_coupon(coupon)
            coupons_cancelled += 1
        except Exception:
            raise RemovalBlocked("O cupom do site desta cliente ainda não pôde ser cancelado. "
                                 "Tente de novo em alguns minutos.") from None

    with transaction.atomic():
        participant = ProgramParticipant.objects.select_for_update().get(pk=participant.pk)
        if participant.status == ProgramParticipant.Status.WITHDRAWN and participant.display_name == REMOVED_NAME:
            return {"already_removed": True, "reversed": 0, "data_result": "erased"}
        # Vale/crédito reservado numa venda de balcão ainda não conferida: devolve antes de estornar.
        for redemption in CounterRedemption.objects.filter(participant=participant,
                                                           state=CounterRedemption.State.RESERVED):
            settle_redemption(redemption.sale, approve=False)
        reversed_total = 0
        wallet = PointWallet.objects.filter(participant=participant).first()
        for lot in (_live_lots(wallet) if wallet else []):
            balances = lot_balances(lot)
            if balances["reserved"]:
                transition_points(lot_id=lot.pk, kind=PointEvent.Kind.CANCEL_RESERVE, amount=balances["reserved"],
                                  idempotency_key=f"remove-unreserve:{lot.pk}")
            balances = lot_balances(lot)
            for bucket, kind in (("pending", PointEvent.Kind.REVERSE_PENDING),
                                 ("available", PointEvent.Kind.REVERSE_AVAILABLE)):
                if balances[bucket]:
                    transition_points(lot_id=lot.pk, kind=kind, amount=balances[bucket],
                                      idempotency_key=f"remove-{bucket}:{lot.pk}")
                    reversed_total += balances[bucket]
        now = timezone.now()
        participant.status = ProgramParticipant.Status.WITHDRAWN
        participant.display_name = REMOVED_NAME
        participant.contact_email = _anonymous_email(participant)
        participant.phone_digest = participant.phone_last4 = ""
        participant.external_customer_id = None
        participant.last_program_activity_at = now
        participant.save(update_fields=["status", "display_name", "contact_email", "phone_digest",
                                        "phone_last4", "external_customer_id", "last_program_activity_at"])
        subs = EnrollmentSubmission.objects.select_for_update().filter(participant=participant)
        link_subs = EnrollmentCustomerLink.objects.filter(participant=participant).values_list("submission_id", flat=True)
        for submission in EnrollmentSubmission.objects.select_for_update().filter(pk__in=list(subs.values_list("pk", flat=True)) + list(link_subs)):
            submission.name = REMOVED_NAME
            submission.email = _anonymous_email(participant)
            submission.phone_digest = submission.phone_last4 = ""
            submission.birth_day = submission.birth_month = None
            submission.marketing_opt_in = False
            submission.withdrawn_at = submission.withdrawn_at or now
            submission.status = EnrollmentSubmission.Status.WITHDRAWN
            submission.save(update_fields=["name", "email", "phone_digest", "phone_last4", "birth_day",
                                           "birth_month", "marketing_opt_in", "withdrawn_at", "status"])
            EnrollmentEmailChallenge.objects.filter(submission=submission, consumed_at__isnull=True).update(consumed_at=now)
        # Vínculo com o cliente da Nuvemshop: o identificador externo sai (libera novo vínculo).
        retained = []
        for link in EnrollmentCustomerLink.objects.select_for_update().filter(participant=participant):
            link.external_customer_id = f"removido-{participant.pk.hex}"[:64]
            link.save(update_fields=["external_customer_id"])
        if not _forget_customer_profile(participant):
            retained.append("customer_profile_contacts")
        from .models import ParticipantRemoval
        ParticipantRemoval.objects.create(
            tenant_id=participant.tenant_id, participant=participant, actor=actor if getattr(actor, "pk", None) else None,
            reason=(reason or "")[:240], reversed_units=reversed_total, coupons_cancelled=coupons_cancelled,
            data_result="retained" if retained else "erased", details={"retained": retained})
        logger.warning("participant_removed tenant=%s participant=%s actor=%s reversed=%s retained=%s",
                       participant.tenant_id, participant.pk, getattr(actor, "pk", None), reversed_total, retained)
    return {"already_removed": False, "reversed": reversed_total, "data_result": "retained" if retained else "erased"}


def _forget_customer_profile(participant):
    """Contatos verificados (hashes) e referências de canal saem: a pessoa pode voltar do zero."""
    from django.db.models import ProtectedError
    from apps.customers.models import ChannelCustomerReference, CustomerProfile, VerifiedCustomerContact
    profile = CustomerProfile.objects.filter(participant=participant).first()
    if profile is None:
        return True
    profile.display_name = REMOVED_NAME
    profile.save(update_fields=["display_name"])
    try:
        with transaction.atomic():
            VerifiedCustomerContact.objects.filter(profile=profile).delete()
            ChannelCustomerReference.objects.filter(profile=profile).delete()
    except ProtectedError:
        # Contato preso a um registro financeiro protegido: fica (só hashes), e a remoção
        # é registrada como "retained" para a loja saber exatamente o que sobrou.
        logger.warning("participant_removed profile_kept tenant=%s", participant.tenant_id)
        return False
    return True


def remove_counter_sale(sale, *, actor, reason):
    """Anula uma venda lançada à mão, por qualquer motivo, tratando TODO o saldo que ela mexeu.

    - Venda ainda não conferida: o vale/crédito reservado nela volta para a cliente.
    - Venda conferida: o que ela gerou e ainda está com a cliente é estornado; o que a cliente
      JÁ USOU é recuperado de outro saldo dela. Sem saldo para recuperar, NADA muda e a loja é
      avisada (RemovalBlocked): venda que gerou benefício gasto não some sem compensação.
    - Crédito/vale usado NA venda anulada volta para a cliente (a compra não valeu).
    A venda some das listas e dos resultados; fica registrada (quem, quando, motivo).
    Devolve (sale, resumo)."""
    from django.db.models import Sum
    from apps.points.models import PointEvent, PointLot
    from apps.points.services import lot_balances, transition_points
    from apps.sales.models import CounterRedemption, SaleRecord
    from apps.sales.pilot import _live_lots, settle_redemption, source_reference
    with transaction.atomic():
        sale = SaleRecord.objects.select_for_update(of=("self",)).get(pk=sale.pk)
        if sale.removed_at:
            return sale, {"already_removed": True}
        summary = {"already_removed": False, "returned": 0, "reversed": 0, "recovered": 0}
        lot = PointLot.objects.select_for_update().filter(tenant_id=sale.tenant_id,
                                                          source_reference=source_reference(sale)).first()
        if lot is not None:
            balances = lot_balances(lot)
            if balances["reserved"]:
                raise RemovalBlocked("O crédito desta venda está reservado em outra venda ainda em aberto. "
                                     "Anule ou confirme aquela venda primeiro.")
            used = PointEvent.objects.filter(lot=lot, kind=PointEvent.Kind.REDEEM).aggregate(t=Sum("amount"))["t"] or 0
            for bucket, kind in (("pending", PointEvent.Kind.REVERSE_PENDING),
                                 ("available", PointEvent.Kind.REVERSE_AVAILABLE)):
                if balances[bucket]:
                    transition_points(lot_id=lot.pk, kind=kind, amount=balances[bucket],
                                      idempotency_key=f"sale-remove-{bucket}:{sale.pk}")
                    summary["reversed"] += balances[bucket]
            if used:
                summary["recovered"] = _recover_used(sale, lot, used, _live_lots, lot_balances, transition_points,
                                                     PointEvent)
        redemption = CounterRedemption.objects.select_for_update().filter(sale=sale).first()
        if redemption and redemption.state == CounterRedemption.State.RESERVED:
            settle_redemption(sale, approve=False)
            summary["returned"] = redemption.points
        elif redemption and redemption.state == CounterRedemption.State.REDEEMED and sale.participant_id:
            summary["returned"] = _restore_counter_credit(sale, redemption)
        sale.removed_at, sale.removed_by, sale.removed_reason = timezone.now(), actor, reason[:240]
        # Libera o número do cupom/pedido para ser lançado de novo, agora certo.
        sale.external_reference = (sale.external_reference[:60] + "~apagada-" + sale.pk.hex[:8])[:80]
        if sale.state in (SaleRecord.State.AWAITING_REVIEW, SaleRecord.State.AWAITING_MEMBER):
            sale.state = SaleRecord.State.REJECTED
        sale.save(update_fields=["removed_at", "removed_by", "removed_reason", "state", "external_reference"])
        logger.warning("counter_sale_removed tenant=%s sale=%s actor=%s summary=%s", sale.tenant_id, sale.pk,
                       getattr(actor, "pk", None), summary)
    return sale, summary


def _recover_used(sale, lot, used, _live_lots, lot_balances, transition_points, PointEvent):
    """Benefício desta venda que a cliente já usou: debita do saldo disponível de outras compras."""
    from apps.points.models import PointWallet
    wallet = PointWallet.objects.filter(pk=lot.wallet_id).first()
    others = [other for other in _live_lots(wallet) if other.pk != lot.pk]
    free = sum(lot_balances(other)["available"] for other in others)
    if free < used:
        money = f"{used / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        raise RemovalBlocked(f"A cliente já usou R$ {money} do benefício desta venda e não tem saldo para devolver. "
                             "A venda não foi anulada: confira com ela ou ajuste numa próxima compra.")
    remaining = used
    for other in others:
        if remaining == 0:
            break
        take = min(lot_balances(other)["available"], remaining)
        if take <= 0:
            continue
        transition_points(lot_id=other.pk, kind=PointEvent.Kind.REVERSE_AVAILABLE, amount=take,
                          idempotency_key=f"sale-recover:{sale.pk}", external_receipt=f"recover:{sale.pk}"[:100])
        remaining -= take
    return used


def _restore_counter_credit(sale, redemption):
    """Crédito/vale usado numa venda que foi apagada volta para a cliente (uma vez)."""
    from datetime import timedelta
    from apps.points.models import PointLot
    from apps.points.services import create_pending_lot
    from apps.sales.models import SaleRecord
    from apps.sales.pilot import RESTORE_RULE
    participant = sale.participant
    ref = f"counter-refund:{sale.pk}"
    if participant.status != ProgramParticipant.Status.ACTIVE or PointLot.objects.filter(
            tenant_id=sale.tenant_id, source_reference=ref).exists():
        return 0
    now = timezone.now()
    paid_at = max(now - timedelta(minutes=1), participant.joined_at, participant.consent_at)
    create_pending_lot(
        participant=participant, channel=SaleRecord.Channel.COUNTER, source_reference=ref,
        eligible_amount_cents=max(redemption.discount_cents, 1), points=redemption.points,
        rule_version=RESTORE_RULE, paid_at=paid_at, unlock_at=paid_at, expires_at=now + timedelta(days=30),
        verification_digest=hashlib.sha256(f"counter-refund|{sale.pk}|{redemption.points}".encode()).hexdigest(),
        restore=True,
    )
    return redemption.points
