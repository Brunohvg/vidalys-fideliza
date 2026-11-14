"""Motor interno de pontos: sem APIs de escrita, jamais usa carteira BRL.

A flag permanece deliberadamente hardcoded OFF no settings. Só testes
isolados podem simular efeitos ao sobrescrevê-la com override_settings.
Uma reconciliação confiável de pagamento ainda NÃO está conectada aqui.
"""
import re
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant
from .models import PointEntry, PointEvent, PointLot, PointWallet

MAX_POINTS = 100_000_000
MAX_CENTS = 100_000_000
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,79}$")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,179}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHANNELS = {"nuvemshop", "counter", "whatsapp", "vidalys_flow"}
MOVEMENTS = {
    PointEvent.Kind.ACCRUE: {"pending": +1},
    PointEvent.Kind.RELEASE: {"pending": -1, "available": +1},
    PointEvent.Kind.RESERVE: {"available": -1, "reserved": +1},
    PointEvent.Kind.CANCEL_RESERVE: {"reserved": -1, "available": +1},
    PointEvent.Kind.REDEEM: {"reserved": -1},
    PointEvent.Kind.REVERSE_PENDING: {"pending": -1},
    PointEvent.Kind.REVERSE_AVAILABLE: {"available": -1},
    PointEvent.Kind.EXPIRE_PENDING: {"pending": -1},
    PointEvent.Kind.EXPIRE_AVAILABLE: {"available": -1},
}


def _enabled():
    if not getattr(settings, "FIDELIZA_POINTS_WRITES_ENABLED", False):
        raise PermissionError("Pontos bloqueados: motor de pagamentos ainda não homologado.")


def _number(value, maximum):
    return type(value) is int and 0 < value <= maximum


def _reference(value, pattern):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def _aware(value):
    return value is not None and timezone.is_aware(value)


def lot_balances(lot):
    result = {"pending": 0, "available": 0, "reserved": 0}
    for row in (PointEntry.objects.filter(event__lot=lot)
                .values("bucket").annotate(total=Sum("delta"))):
        result[row["bucket"]] = row["total"]
    return result


def wallet_balances(wallet):
    if wallet is None:
        return None
    result = {"pending": 0, "available": 0, "reserved": 0}
    for row in (PointEntry.objects.filter(event__lot__wallet=wallet)
                .values("bucket").annotate(total=Sum("delta"))):
        result[row["bucket"]] = row["total"]
    return result


def _post(lot, kind, amount, key, *, external_receipt=""):
    if not _number(amount, MAX_POINTS) or not _reference(key, KEY_PATTERN):
        raise ValueError("Quantidade ou chave inválida.")
    if kind not in MOVEMENTS:
        raise ValueError("Evento inválido.")
    if not isinstance(external_receipt, str) or len(external_receipt) > 100:
        raise ValueError("Referência de comprovação inválida.")
    existing = PointEvent.objects.filter(lot=lot, idempotency_key=key).first()
    if existing:
        if (existing.kind != kind or existing.amount != amount or
                existing.external_receipt != external_receipt):
            raise ValueError("Chave reutilizada com conteúdo divergente.")
        return existing, False
    balances = lot_balances(lot)
    deltas = {bucket: multiplier * amount for bucket,multiplier in MOVEMENTS[kind].items()}
    for bucket,delta in deltas.items():
        if balances[bucket] + delta < 0:
            raise ValueError("Saldo de pontos insuficiente.")
    event = PointEvent.objects.create(
        lot=lot, kind=kind, amount=amount,
        idempotency_key=key, external_receipt=external_receipt,
    )
    PointEntry.objects.bulk_create([
        PointEntry(event=event,bucket=bucket,delta=delta)
        for bucket,delta in deltas.items()
    ])
    return event, True


@transaction.atomic
def create_pending_lot(*, participant, channel, source_reference,
                       eligible_amount_cents, points, rule_version,
                       paid_at, unlock_at, expires_at, verification_digest):
    """Domínio interno; digest fornecido não é prova independente de pagamento."""
    _enabled()
    if (not isinstance(participant, ProgramParticipant)
            or participant.pk is None
            or participant.status != ProgramParticipant.Status.ACTIVE):
        raise ValueError("Participante ativo obrigatório.")
    if (channel not in CHANNELS or
            not _reference(source_reference,SOURCE_PATTERN) or
            not _number(eligible_amount_cents, MAX_CENTS) or
            not _number(points, MAX_POINTS) or
            not isinstance(rule_version, str) or
            not 1 <= len(rule_version) <= 40 or
            not _reference(rule_version, KEY_PATTERN) or
            not _reference(verification_digest,HASH_PATTERN) or
            not all(_aware(x) for x in (paid_at,unlock_at,expires_at)) or
            paid_at > timezone.now() or
            paid_at < max(participant.joined_at, participant.consent_at) or
            not paid_at <= unlock_at < expires_at):
        raise ValueError("Compra, regra ou datas inválidas.")
    tenant = Tenant.objects.select_for_update().get(pk=participant.tenant_id)
    if tenant.status != Tenant.Status.ACTIVE:
        raise ValueError("Empresa inativa.")
    existing = PointLot.objects.select_related("wallet").filter(
        tenant=tenant, channel=channel, source_reference=source_reference,
    ).first()
    if existing:
        if (
            existing.wallet.participant_id != participant.pk or
            existing.eligible_amount_cents != eligible_amount_cents or
            existing.points_issued != points or
            existing.rule_version != rule_version or
            existing.source_paid_at != paid_at or
            existing.unlock_at != unlock_at or
            existing.expires_at != expires_at or
            existing.verification_digest != verification_digest
        ):
            raise ValueError("A mesma compra foi apresentada com outro valor ou participante.")
        return existing, False
    wallet, _ = PointWallet.objects.get_or_create(
        participant=participant,
        defaults={"tenant":tenant},
    )
    if wallet.tenant_id != tenant.pk:
        raise ValueError("Carteira e empresa divergentes.")
    lot = PointLot.objects.create(
        tenant=tenant, wallet=wallet, channel=channel,
        source_reference=source_reference,
        eligible_amount_cents=eligible_amount_cents,
        source_paid_at=paid_at,
        verification_digest=verification_digest,
        rule_version=rule_version,
        points_issued=points, unlock_at=unlock_at,
        expires_at=expires_at,
    )
    _post(lot, PointEvent.Kind.ACCRUE, points, "accrue:"+source_reference)
    return lot, True


@transaction.atomic
def transition_points(*, lot_id, kind, amount, idempotency_key, external_receipt=""):
    """Transição interna transacional; somente futuro adaptador autorizado."""
    _enabled()
    lot = PointLot.objects.select_for_update().select_related(
        "wallet__participant","tenant",
    ).get(pk=lot_id)
    # Bloquear leitura/escrita entre tenants depende do adaptador; esta função
    # NÃO deve ser exposta como endpoint do usuário final.
    now = timezone.now()
    if kind == PointEvent.Kind.ACCRUE:
        raise ValueError("Crédito deve ser criado por create_pending_lot.")
    if kind in (PointEvent.Kind.RELEASE, PointEvent.Kind.RESERVE):
        if lot.tenant.status != Tenant.Status.ACTIVE:
            raise ValueError("Empresa inativa.")
        if lot.wallet.participant.status != ProgramParticipant.Status.ACTIVE:
            raise ValueError("Participante inativo.")
    if kind == PointEvent.Kind.RELEASE:
        if now < lot.unlock_at or now >= lot.expires_at:
            raise ValueError("Carência não cumprida ou pontos expirados.")
    elif kind in (PointEvent.Kind.RESERVE, PointEvent.Kind.CANCEL_RESERVE):
        if now >= lot.expires_at:
            raise ValueError("Pontos expirados; reserva indisponível.")
    elif kind in (PointEvent.Kind.EXPIRE_PENDING, PointEvent.Kind.EXPIRE_AVAILABLE):
        if now < lot.expires_at:
            raise ValueError("Expiração ainda não atingida.")
    if kind == PointEvent.Kind.REDEEM and not external_receipt:
        raise ValueError("Resgate exige prova de benefício aplicado.")
    return _post(lot,kind,amount,idempotency_key,external_receipt=external_receipt)
