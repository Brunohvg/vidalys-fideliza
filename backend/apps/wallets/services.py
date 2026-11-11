"""Operações transacionais internas. Não expor este serviço em endpoints públicos.

FIDELIZA_LEDGER_WRITES_ENABLED permanece False até existir ingestão verificável
de pedidos pagos, política de liberação e autorização formal do piloto.
"""
from django.conf import settings
from django.db import transaction
from django.db.models import Sum

from apps.participants.models import ProgramParticipant
from .models import CashbackEntry, CashbackEvent, CashbackWallet

MAX_EVENT_CENTS = 100_000_000  # R$ 1 milhão por evento, limite defensivo interno

MOVEMENTS = {
    CashbackEvent.Kind.ACCRUAL: {"pending": 1},
    CashbackEvent.Kind.RELEASE: {"pending": -1, "available": 1},
    CashbackEvent.Kind.RESERVE: {"available": -1, "reserved": 1},
    CashbackEvent.Kind.CANCEL_RESERVATION: {"reserved": -1, "available": 1},
    CashbackEvent.Kind.REDEEM: {"reserved": -1},
    CashbackEvent.Kind.EXPIRE: {"available": -1},
    CashbackEvent.Kind.REVERSE_PENDING: {"pending": -1},
    CashbackEvent.Kind.REVERSE_AVAILABLE: {"available": -1},
}


def wallet_balances(wallet):
    """Soma do ledger, não um saldo mutável que possa divergir da trilha."""
    result = {"pending_cents": 0, "available_cents": 0, "reserved_cents": 0}
    if wallet is None:
        return None
    rows = (CashbackEntry.objects.filter(event__wallet=wallet)
            .values("bucket").annotate(total=Sum("delta_cents")))
    for row in rows:
        result[row["bucket"] + "_cents"] = row["total"]
    return result


def balances_for_participants(*, tenant_id, participant_ids):
    """Consulta agrupada para a tela de participantes, sem N+1."""
    wallets = list(CashbackWallet.objects.filter(
        tenant_id=tenant_id, participant_id__in=participant_ids
    ).values("id", "participant_id"))
    if not wallets:
        return {}
    ids = [wallet["id"] for wallet in wallets]
    balances = {
        wallet["participant_id"]: {
            "pending_cents": 0, "available_cents": 0, "reserved_cents": 0,
        }
        for wallet in wallets
    }
    by_wallet = {wallet["id"]: wallet["participant_id"] for wallet in wallets}
    rows = (CashbackEntry.objects.filter(event__wallet_id__in=ids)
            .values("event__wallet_id", "bucket").annotate(total=Sum("delta_cents")))
    for row in rows:
        participant_id = by_wallet[row["event__wallet_id"]]
        balances[participant_id][row["bucket"] + "_cents"] = row["total"]
    return balances


@transaction.atomic
def append_cashback_event(
    *, participant, kind, amount_cents, idempotency_key, source_order_id="", rule_version=""
):
    """Somente pipeline interno futuro; sem permissão de gravação por HTTP.

    A verificação independente de pagamento/entrega ainda NÃO foi implementada.
    O feature flag bloqueia toda concessão/reserva até existir esse pipeline.
    """
    if not getattr(settings, "FIDELIZA_LEDGER_WRITES_ENABLED", False):
        raise PermissionError("Lançamentos desabilitados até validar a integração de pagamentos.")
    if kind not in MOVEMENTS:
        raise ValueError("Tipo de evento não reconhecido.")
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or not 0 < amount_cents <= MAX_EVENT_CENTS:
        raise ValueError("Valor em centavos inválido.")
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 180 or not idempotency_key.isascii():
        raise ValueError("Chave de idempotência inválida.")
    if not isinstance(rule_version, str) or not 1 <= len(rule_version) <= 40:
        raise ValueError("Versão da regra obrigatória.")
    if not isinstance(source_order_id, str) or len(source_order_id) > 80:
        raise ValueError("Referência do pedido inválida.")
    if kind in {CashbackEvent.Kind.ACCRUAL, CashbackEvent.Kind.REDEEM} and not source_order_id:
        raise ValueError("Pedido verificado deve ser referenciado.")
    if participant.status != ProgramParticipant.Status.ACTIVE and kind in {
        CashbackEvent.Kind.ACCRUAL, CashbackEvent.Kind.RESERVE
    }:
        raise ValueError("Não conceder nem reservar a participante inativo.")

    wallet, _ = CashbackWallet.objects.get_or_create(
        participant=participant,
        defaults={"tenant_id": participant.tenant_id},
    )
    wallet = CashbackWallet.objects.select_for_update().get(pk=wallet.pk)
    if wallet.tenant_id != participant.tenant_id:
        raise ValueError("Participante e carteira de lojas diferentes.")

    previous = CashbackEvent.objects.filter(
        wallet=wallet, idempotency_key=idempotency_key,
    ).first()
    if previous:
        if (
            previous.kind != kind or previous.amount_cents != amount_cents
            or previous.source_order_id != source_order_id
            or previous.rule_version != rule_version
        ):
            raise ValueError("Chave idempotente reutilizada com conteúdo diferente.")
        return previous, False

    deltas = {bucket: multiplier * amount_cents for bucket, multiplier in MOVEMENTS[kind].items()}
    balances = wallet_balances(wallet)
    for bucket, delta in deltas.items():
        if balances[bucket + "_cents"] + delta < 0:
            raise ValueError("Saldo insuficiente; operação rejeitada.")

    event = CashbackEvent.objects.create(
        wallet=wallet, kind=kind, amount_cents=amount_cents,
        idempotency_key=idempotency_key,
        source_order_id=source_order_id, rule_version=rule_version,
    )
    CashbackEntry.objects.bulk_create([
        CashbackEntry(event=event, bucket=bucket, delta_cents=delta)
        for bucket, delta in deltas.items()
    ])
    return event, True
