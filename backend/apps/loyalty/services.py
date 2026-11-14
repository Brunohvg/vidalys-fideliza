"""Motor interno loyalty: cálculo puro e execução transacional sob gates fechados.

O pedido 'paid' do canal NÃO equivale a captura PSP. Sem evidência de origem
habilitada + custo conferido + budget + identidade, NUNCA escreve ledger.
Os testes isolados sobrescrevem as flags para simular o ciclo financeiro.
"""
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.costs.models import CostItem
from apps.margin.services import simulate_margin
from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent, PointLot, PointWallet
from apps.points.services import (
    create_pending_lot, lot_balances, transition_points, wallet_balances as point_wallet_balances,
)
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEvent, CashbackWallet
from apps.wallets.services import append_cashback_event, wallet_balances as cashback_wallet_balances

from .models import (
    FinancialEvidence, LoyaltyEngagement, LoyaltyGrant, LoyaltyRecovery, LoyaltyRule,
    LoyaltyTier, LoyaltyVoucher, MemberTierSnapshot, VoucherPointAllocation,
)

SAFE_RECEIPT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,99}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_CENTS = 100_000_000
MAX_POINTS = 100_000_000
REDEMPTION_CHANNELS = {"counter", "vidalys_flow"}


class LoyaltyBlocked(ValueError):
    """Regra financeira incompleta, conflito, margem ausente ou prova inválida."""


@dataclass(frozen=True)
class OrderCosts:
    """Dados por item conferidos na loja (não afirma vínculo com pedido remoto)."""
    # Tuplas (cost_item_id, quantity) com referência a CostItem verificado.
    lines: tuple
    payment_fee_cents: int
    shipping_subsidy_cents: int
    other_variable_costs_cents: int = 0


@dataclass(frozen=True)
class RewardQuote:
    points: int
    cashback_cents: int
    exposure_cents: int
    tier_name: str
    second_purchase: bool


def _integer(value, *, minimum=0, maximum=MAX_CENTS):
    return type(value) is int and minimum <= value <= maximum


def _execution_enabled():
    # Todas as flags continuam False no settings real. Somente testes
    # de domínio isolados podem usar override_settings.
    if not (
        getattr(settings, "FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED", False)
        and getattr(settings, "FIDELIZA_POINTS_WRITES_ENABLED", False)
        and getattr(settings, "FIDELIZA_LEDGER_WRITES_ENABLED", False)
    ):
        raise PermissionError("Operação financeira de fidelidade bloqueada.")


def _evidence(evidence, *, kind, sale, amount):
    authorized = getattr(settings, "FIDELIZA_TRUSTED_PAYMENT_ADAPTERS", frozenset())
    if (
        not isinstance(evidence, FinancialEvidence)
        or evidence.kind != kind
        or evidence.tenant_id != sale.tenant_id
        or evidence.sale_id != sale.pk
        or evidence.provider not in authorized
        or not SHA256.fullmatch(evidence.verification_digest)
        or not _integer(evidence.amount_cents, minimum=1)
        or evidence.amount_cents != amount
        or timezone.is_naive(evidence.occurred_at)
        or timezone.is_naive(evidence.verified_at)
        or evidence.occurred_at > timezone.now()
        or evidence.verified_at < evidence.occurred_at
    ):
        raise LoyaltyBlocked("Sem comprovação financeira independente válida.")


def _rule(tenant):
    result = LoyaltyRule.objects.filter(tenant=tenant, enabled=True).first()
    if not result or (result.points_per_unit == 0 and result.cashback_bps == 0):
        raise LoyaltyBlocked("Programa sem regra ativa de acúmulo.")
    if (
        not 1 <= result.points_per_cents <= MAX_CENTS
        or not 1 <= result.point_value_cents <= MAX_CENTS
        or not 0 <= result.cashback_bps <= 10000
        or not 0 <= result.hold_days <= 90
        or not 1 <= result.validity_days <= 1095
        or not 0 <= result.minimum_margin_bps <= 10000
        or not 10000 <= result.second_purchase_multiplier_bps <= 30000
        or not 1 <= result.second_purchase_window_days <= 365
        or not 1 <= result.budget_cents <= 1_000_000_000
    ):
        raise LoyaltyBlocked("Regra fora dos limites operacionais.")
    return result


def choose_tier(*, rule, rolling_spend_cents):
    """Determina nível SEM depender da Nuvemshop ou alterar saldo."""
    if not _integer(rolling_spend_cents, maximum=1_000_000_000_000):
        raise ValueError("Histórico inválido.")
    tiers = list(LoyaltyTier.objects.filter(rule=rule).order_by("minimum_spend_cents"))
    if not tiers or tiers[0].minimum_spend_cents != 0:
        raise LoyaltyBlocked("Configure o primeiro nível VIP com mínimo zero.")
    return next(
        (tier for tier in reversed(tiers) if tier.minimum_spend_cents <= rolling_spend_cents),
        tiers[0],
    )


def calculate_reward(*, rule, eligible_cents, tier, prior_count=0, days_since_first=None):
    """Apenas inteiros; sem emissão ou aprovação automática."""
    if not _integer(eligible_cents, minimum=1) or not _integer(prior_count, maximum=100_000):
        raise ValueError("Valor ou histórico inválido.")
    if tier.rule_id != rule.pk:
        raise LoyaltyBlocked("Nível VIP pertence a outra regra.")
    second = (
        prior_count == 1 and days_since_first is not None
        and 0 <= days_since_first <= rule.second_purchase_window_days
    )
    multiplier = rule.second_purchase_multiplier_bps if second else 10000
    scale = tier.multiplier_bps * multiplier
    points = eligible_cents * rule.points_per_unit * scale // (rule.points_per_cents * 100_000_000)
    cashback = eligible_cents * rule.cashback_bps * scale // 1_000_000_000_000
    exposure = points * rule.point_value_cents + cashback
    if points > MAX_POINTS or cashback > MAX_CENTS or exposure > MAX_CENTS:
        raise LoyaltyBlocked("Recompensa excede os limites de segurança.")
    return RewardQuote(
        points=points, cashback_cents=cashback,
        exposure_cents=exposure, tier_name=tier.name,
        second_purchase=second,
    )


def _prior_grants(*, tenant, participant, captured_at):
    since = captured_at - timedelta(days=365)
    return list(LoyaltyGrant.objects.filter(
        tenant=tenant, participant=participant, captured_at__gte=since,
        captured_at__lt=captured_at,
        status__in=[LoyaltyGrant.Status.PENDING, LoyaltyGrant.Status.RELEASED],
    ).order_by("captured_at", "pk"))


def _rolling_spend(*, tenant, participant, as_of):
    since = as_of - timedelta(days=365)
    return (
        LoyaltyGrant.objects.filter(
            tenant=tenant, participant=participant,
            captured_at__gte=since, captured_at__lte=as_of,
            status__in=[LoyaltyGrant.Status.PENDING, LoyaltyGrant.Status.RELEASED],
        ).aggregate(total=Sum("eligible_amount_cents"))["total"] or 0
    )


def _update_tier(*, tenant, participant, rule, now):
    spent = _rolling_spend(tenant=tenant, participant=participant, as_of=now)
    tier = choose_tier(rule=rule, rolling_spend_cents=spent)
    MemberTierSnapshot.objects.update_or_create(
        participant=participant,
        defaults={"tenant": tenant, "rule": rule, "tier": tier, "rolling_spend_cents": spent},
    )


def _verified_cogs(*, tenant, costs):
    if not isinstance(costs, OrderCosts) or not costs.lines:
        raise LoyaltyBlocked("Custos de itens obrigatórios; falta referência de SKU.")
    expenses = (costs.payment_fee_cents, costs.shipping_subsidy_cents, costs.other_variable_costs_cents)
    if any(not _integer(x) for x in expenses):
        raise LoyaltyBlocked("Despesas variáveis inválidas ou ausentes.")
    seen, total = set(), 0
    for item_id, qty in costs.lines:
        if item_id in seen or not _integer(qty, minimum=1, maximum=10000):
            raise LoyaltyBlocked("Itens repetidos ou quantidade inválida.")
        seen.add(item_id)
        item = CostItem.objects.filter(pk=item_id, tenant=tenant).first()
        if (
            not item or item.verified_at is None
            or item.unit_cost_cents is None or not item.sku and not item.external_variant_id
        ):
            raise LoyaltyBlocked("SKU/variante sem custo individual conferido.")
        total += item.unit_cost_cents * qty
    if total > MAX_CENTS:
        raise LoyaltyBlocked("Custo supera limite por pedido.")
    return total


def sale_readiness(*, sale):
    """Diagnóstico somente leitura para transição de estado PR #19."""
    if sale.order_status != SaleRecord.OrderStatus.PAID:
        return "order_not_reported_paid"
    if not sale.customer_profile_id or not sale.customer_profile.participant_id:
        return "identity_not_verified"
    if not FinancialEvidence.objects.filter(
        sale=sale, kind=FinancialEvidence.Kind.CAPTURE,
    ).exists():
        return "requires_independent_capture"
    return "requires_cost_margin_and_budget_check"


@transaction.atomic
def grant_for_captured_sale(*, sale_id, evidence_id, costs):
    """Ingestão 'paid' nunca chama este executor; exige evidência verificada."""
    _execution_enabled()
    # Lock único por tenant serializa duas compras e orçamento da loja.
    base = SaleRecord.objects.get(pk=sale_id)
    tenant = Tenant.objects.select_for_update().get(pk=base.tenant_id, status=Tenant.Status.ACTIVE)
    sale = SaleRecord.objects.select_related("customer_profile__participant").get(pk=sale_id, tenant=tenant)
    existing = LoyaltyGrant.objects.filter(sale=sale).first()
    if existing:
        if str(existing.evidence_id) != str(evidence_id):
            raise LoyaltyBlocked("Pedido já processado com outra comprovação.")
        return existing, False
    if sale.order_status != SaleRecord.OrderStatus.PAID or sale.reported_total_cents <= 0:
        raise LoyaltyBlocked("Pedido não está elegível como pagamento.")
    profile = sale.customer_profile
    participant = profile.participant if profile else None
    if (
        not participant or participant.tenant_id != tenant.pk
        or participant.status != ProgramParticipant.Status.ACTIVE
        or not profile.verified_contacts.exists()
    ):
        raise LoyaltyBlocked("Compra não vinculada a participante com identidade verificada.")
    evidence = FinancialEvidence.objects.get(pk=evidence_id)
    _evidence(evidence, kind=FinancialEvidence.Kind.CAPTURE, sale=sale, amount=sale.reported_total_cents)
    if evidence.occurred_at < max(participant.joined_at, participant.consent_at):
        raise LoyaltyBlocked("Compra anterior à adesão verificada.")
    if LoyaltyRecovery.objects.filter(
        grant__tenant=tenant, grant__participant=participant, resolved_at__isnull=True,
    ).exists():
        raise LoyaltyBlocked("Participante possui pendência de recuperação.")
    rule = _rule(tenant)
    prior = _prior_grants(tenant=tenant, participant=participant, captured_at=evidence.occurred_at)
    spent = sum(item.eligible_amount_cents for item in prior)
    tier = choose_tier(rule=rule, rolling_spend_cents=spent)
    days = (evidence.occurred_at - prior[0].captured_at).days if len(prior) == 1 else None
    quote = calculate_reward(
        rule=rule, eligible_cents=sale.reported_total_cents,
        tier=tier, prior_count=len(prior), days_since_first=days,
    )
    if quote.exposure_cents <= 0:
        raise LoyaltyBlocked("Regra não gera benefício positivo para esta compra.")
    # O módulo costs armazena custos conferidos por variante. O PR #19
    # ainda não traz as linhas do pedido para comparar; portanto a execução
    # só fica disponível em testes sintéticos até G7+G8.
    cogs = _verified_cogs(tenant=tenant, costs=costs)
    margin = simulate_margin({
        "eligible_subtotal_cents": sale.reported_total_cents,
        "existing_discounts_cents": 0,
        "cost_of_goods_cents": cogs,
        "payment_fee_cents": costs.payment_fee_cents,
        "shipping_subsidy_cents": costs.shipping_subsidy_cents,
        "other_variable_costs_cents": costs.other_variable_costs_cents,
        "proposed_cashback_bps": 0,
        "minimum_margin_bps": rule.minimum_margin_bps,
    })
    if margin["status"] != "within_target" or quote.exposure_cents > margin["safe_cashback_budget_cents"]:
        raise LoyaltyBlocked("Exposição do benefício ultrapassa a margem segura.")
    committed = LoyaltyGrant.objects.filter(rule=rule).aggregate(
        total=Sum("exposure_cents")
    )["total"] or 0
    if committed + quote.exposure_cents > rule.budget_cents:
        raise LoyaltyBlocked("Orçamento comprometido; concessão negada.")
    now = timezone.now()
    unlock_at = evidence.occurred_at + timedelta(days=rule.hold_days)
    expires_at = unlock_at + timedelta(days=rule.validity_days)
    if expires_at <= now:
        raise LoyaltyBlocked("Benefício expirado antes da concessão.")
    version = f"rule:{rule.version}"
    lot = None
    event = None
    if quote.points:
        lot, _ = create_pending_lot(
            participant=participant, channel=sale.channel,
            source_reference=sale.external_reference,
            eligible_amount_cents=sale.reported_total_cents, points=quote.points,
            rule_version=version, paid_at=evidence.occurred_at,
            unlock_at=unlock_at, expires_at=expires_at,
            verification_digest=evidence.verification_digest,
        )
    if quote.cashback_cents:
        event, _ = append_cashback_event(
            participant=participant, kind=CashbackEvent.Kind.ACCRUAL,
            amount_cents=quote.cashback_cents,
            idempotency_key=f"sale:{sale.pk}:rule:{rule.pk}:accrual",
            source_order_id=str(sale.pk), rule_version=version,
        )
    grant = LoyaltyGrant.objects.create(
        tenant=tenant, sale=sale, participant=participant, rule=rule,
        evidence=evidence, point_lot=lot, cashback_event=event,
        points_issued=quote.points, cashback_cents=quote.cashback_cents,
        exposure_cents=quote.exposure_cents, eligible_amount_cents=sale.reported_total_cents,
        captured_at=evidence.occurred_at, unlock_at=unlock_at, expires_at=expires_at,
    )
    _update_tier(tenant=tenant, participant=participant, rule=rule, now=now)
    return grant, True


@transaction.atomic
def release_grant(*, grant_id):
    """Carência cumprida; idempotente e restrito ao grant aprovado."""
    _execution_enabled()
    base = LoyaltyGrant.objects.get(pk=grant_id)
    tenant = Tenant.objects.select_for_update().get(pk=base.tenant_id, status=Tenant.Status.ACTIVE)
    grant = LoyaltyGrant.objects.select_for_update().get(pk=grant_id, tenant=tenant)
    if grant.status == LoyaltyGrant.Status.RELEASED:
        return grant, False
    if grant.status != LoyaltyGrant.Status.PENDING:
        raise LoyaltyBlocked("Concessão revertida ou indisponível.")
    if grant.participant.status != ProgramParticipant.Status.ACTIVE:
        raise LoyaltyBlocked("Participante sem adesão ativa.")
    if grant.sale.order_status != SaleRecord.OrderStatus.PAID:
        raise LoyaltyBlocked("Pedido alterado: revalide antes de liberar saldo.")
    now = timezone.now()
    if now < grant.unlock_at or now >= grant.expires_at:
        raise LoyaltyBlocked("Carência não cumprida ou validade encerrada.")
    if grant.point_lot_id:
        pending = lot_balances(grant.point_lot)["pending"]
        if pending != grant.points_issued:
            raise LoyaltyBlocked("Lote de pontos sofreu movimentação inesperada.")
        transition_points(
            lot_id=grant.point_lot_id, kind=PointEvent.Kind.RELEASE,
            amount=pending, idempotency_key=f"grant:{grant.pk}:release",
        )
    if grant.cashback_event_id:
        wallet = grant.cashback_event.wallet
        if cashback_wallet_balances(wallet)["pending_cents"] < grant.cashback_cents:
            raise LoyaltyBlocked("Pendente de cashback insuficiente.")
        append_cashback_event(
            participant=grant.participant, kind=CashbackEvent.Kind.RELEASE,
            amount_cents=grant.cashback_cents,
            idempotency_key=f"grant:{grant.pk}:release",
            source_order_id=str(grant.sale_id), rule_version=f"rule:{grant.rule.version}",
        )
    grant.status = LoyaltyGrant.Status.RELEASED
    grant.save(update_fields=["status"])
    return grant, True



def _code_digests(code):
    if not isinstance(code, str) or not re.fullmatch(r"VF[A-F0-9]{24}", code):
        raise LoyaltyBlocked("Voucher inválido.")
    keys = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return [
        salted_hmac("vidalys.voucher.v1", code, secret=key, algorithm="sha256").hexdigest()
        for key in keys
    ]


def verify_voucher(*, tenant_id, code):
    """Consulta de validade sem revelar identidade do titular."""
    match = LoyaltyVoucher.objects.filter(
        tenant_id=tenant_id, code_digest__in=_code_digests(code),
    ).select_related("participant").first()
    if not match:
        return {"valid": False, "reason": "not_found"}
    if match.state != LoyaltyVoucher.State.RESERVED:
        return {"valid": False, "reason": "not_available"}
    if match.expires_at <= timezone.now():
        return {"valid": False, "reason": "expired"}
    if LoyaltyRecovery.objects.filter(
        grant__tenant_id=tenant_id, grant__participant_id=match.participant_id,
        resolved_at__isnull=True,
    ).exists():
        return {"valid": False, "reason": "recovery_pending"}
    return {
        "valid": True, "unit": match.unit,
        "amount": match.amount, "discount_cents": match.discount_cents,
        "expires_at": match.expires_at.isoformat(),
    }


@transaction.atomic
def issue_voucher(*, tenant_id, participant_id, unit, amount):
    """Reserva carteira e cria voucher único sem disponibilizar cupom na Nuvemshop."""
    _execution_enabled()
    if unit not in LoyaltyVoucher.Unit.values or not _integer(amount, minimum=1):
        raise LoyaltyBlocked("Unidade ou quantidade inválida.")
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id, status=Tenant.Status.ACTIVE)
    participant = ProgramParticipant.objects.get(
        pk=participant_id, tenant=tenant, status=ProgramParticipant.Status.ACTIVE,
    )
    if not getattr(participant, "customer_profile", None):
        raise LoyaltyBlocked("Participante não possui perfil unificado.")
    if not participant.customer_profile.verified_contacts.exists():
        raise LoyaltyBlocked("Participante sem contato verificado.")
    if LoyaltyRecovery.objects.filter(
        grant__tenant=tenant, grant__participant=participant,
        resolved_at__isnull=True,
    ).exists():
        raise LoyaltyBlocked("Resgate suspenso por recuperação de saldo.")
    if LoyaltyGrant.objects.filter(
        tenant=tenant, participant=participant,
        sale__order_status__in=[
            SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED,
        ],
        status__in=[LoyaltyGrant.Status.PENDING, LoyaltyGrant.Status.RELEASED],
    ).exists():
        raise LoyaltyBlocked("Venda estornada ainda exige reconciliação.")
    rule = _rule(tenant)
    now = timezone.now()
    if not LoyaltyGrant.objects.filter(
        tenant=tenant, participant=participant, status=LoyaltyGrant.Status.RELEASED,
        expires_at__gt=now,
    ).exists():
        raise LoyaltyBlocked("Não existe benefício confirmado e válido.")
    discount = amount * rule.point_value_cents if unit == LoyaltyVoucher.Unit.POINTS else amount
    if not 0 < discount <= MAX_CENTS:
        raise LoyaltyBlocked("Valor de desconto fora do limite.")
    token = "VF" + secrets.token_hex(12).upper()
    voucher = LoyaltyVoucher.objects.create(
        tenant=tenant, participant=participant, rule=rule,
        code_digest=_code_digests(token)[0],
        unit=unit, amount=amount, discount_cents=discount,
        expires_at=now + timedelta(days=7),
    )
    if unit == LoyaltyVoucher.Unit.POINTS:
        wallet = PointWallet.objects.filter(participant=participant, tenant=tenant).first()
        if not wallet or point_wallet_balances(wallet)["available"] < amount:
            raise LoyaltyBlocked("Pontos disponíveis insuficientes.")
        remaining = amount
        # FIFO pelo vencimento da compra. Não reservar valores pendentes/expirados.
        for lot in PointLot.objects.filter(
            wallet=wallet, tenant=tenant, expires_at__gt=now,
        ).order_by("expires_at", "pk"):
            available = lot_balances(lot)["available"]
            take = min(available, remaining)
            if take <= 0:
                continue
            transition_points(
                lot_id=lot.pk, kind=PointEvent.Kind.RESERVE, amount=take,
                idempotency_key=f"voucher:{voucher.pk}:reserve:{lot.pk}",
            )
            VoucherPointAllocation.objects.create(voucher=voucher, lot=lot, amount=take)
            voucher.expires_at = min(voucher.expires_at, lot.expires_at)
            remaining -= take
            if not remaining:
                break
        if remaining:
            raise LoyaltyBlocked("Lotes disponíveis insuficientes.")
        voucher.save(update_fields=["expires_at"])
    else:
        wallet = CashbackWallet.objects.filter(participant=participant, tenant=tenant).first()
        if not wallet or cashback_wallet_balances(wallet)["available_cents"] < amount:
            raise LoyaltyBlocked("Cashback disponível insuficiente.")
        append_cashback_event(
            participant=participant, kind=CashbackEvent.Kind.RESERVE,
            amount_cents=amount,
            idempotency_key=f"voucher:{voucher.pk}:reserve",
            source_order_id=str(voucher.pk), rule_version=f"rule:{rule.version}",
        )
    return voucher, token


def _cancel_reserved_voucher(voucher):
    if voucher.state != LoyaltyVoucher.State.RESERVED:
        return False
    if voucher.unit == LoyaltyVoucher.Unit.POINTS:
        for allocation in VoucherPointAllocation.objects.filter(voucher=voucher).select_related("lot"):
            transition_points(
                lot_id=allocation.lot_id, kind=PointEvent.Kind.CANCEL_RESERVE,
                amount=allocation.amount,
                idempotency_key=f"voucher:{voucher.pk}:cancel:{allocation.lot_id}",
            )
            # Se o lote já venceu, os pontos devolvidos não ficam disponíveis.
            if allocation.lot.expires_at <= timezone.now():
                transition_points(
                    lot_id=allocation.lot_id, kind=PointEvent.Kind.EXPIRE_AVAILABLE,
                    amount=allocation.amount,
                    idempotency_key=f"voucher:{voucher.pk}:expire:{allocation.lot_id}",
                )
    else:
        append_cashback_event(
            participant=voucher.participant,
            kind=CashbackEvent.Kind.CANCEL_RESERVATION, amount_cents=voucher.amount,
            idempotency_key=f"voucher:{voucher.pk}:cancel",
            source_order_id=str(voucher.pk), rule_version=f"rule:{voucher.rule.version}",
        )
    voucher.state = LoyaltyVoucher.State.CANCELLED
    voucher.save(update_fields=["state"])
    return True


@transaction.atomic
def cancel_voucher(*, tenant_id, voucher_id):
    """Revoga uma reserva interna; não cancela cupons criados fora da aplicação."""
    _execution_enabled()
    Tenant.objects.select_for_update().get(pk=tenant_id, status=Tenant.Status.ACTIVE)
    voucher = LoyaltyVoucher.objects.select_for_update().get(pk=voucher_id, tenant_id=tenant_id)
    if voucher.state == LoyaltyVoucher.State.REDEEMED:
        raise LoyaltyBlocked("Voucher utilizado exige reconciliação externa.")
    return _cancel_reserved_voucher(voucher)


@transaction.atomic
def redeem_voucher(*, tenant_id, code, channel, external_receipt):
    """Baixa uma reserva SOMENTE após confirmação de aplicação pelo canal autorizado.

    O endpoint de produção permanece desativado. Um recibo fornecido por
    formulário NÃO equivale a comprovante de checkout Nuvemshop.
    """
    _execution_enabled()
    if channel not in REDEMPTION_CHANNELS or (
        not isinstance(external_receipt, str)
        or not SAFE_RECEIPT.fullmatch(external_receipt)
    ):
        raise LoyaltyBlocked("Referência de resgate inválida.")
    Tenant.objects.select_for_update().get(pk=tenant_id, status=Tenant.Status.ACTIVE)
    voucher = LoyaltyVoucher.objects.select_for_update().filter(
        tenant_id=tenant_id, code_digest__in=_code_digests(code),
    ).first()
    if not voucher:
        raise LoyaltyBlocked("Voucher não encontrado.")
    if voucher.state == LoyaltyVoucher.State.REDEEMED:
        if (voucher.redemption_channel, voucher.redemption_reference) == (channel, external_receipt):
            return voucher, False
        raise LoyaltyBlocked("Voucher já utilizado.")
    if voucher.state != LoyaltyVoucher.State.RESERVED or voucher.expires_at <= timezone.now():
        raise LoyaltyBlocked("Voucher indisponível ou expirado.")
    if voucher.participant.status != ProgramParticipant.Status.ACTIVE:
        raise LoyaltyBlocked("Participante não está ativo.")
    if LoyaltyRecovery.objects.filter(
        grant__tenant_id=tenant_id, grant__participant=voucher.participant,
        resolved_at__isnull=True,
    ).exists():
        raise LoyaltyBlocked("Saldo em recuperação.")
    if LoyaltyGrant.objects.filter(
        tenant_id=tenant_id, participant=voucher.participant,
        sale__order_status__in=[
            SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED,
        ],
        status__in=[LoyaltyGrant.Status.PENDING, LoyaltyGrant.Status.RELEASED],
    ).exists():
        raise LoyaltyBlocked("Venda estornada ainda exige reconciliação.")
    if LoyaltyVoucher.objects.filter(
        tenant_id=tenant_id, redemption_channel=channel,
        redemption_reference=external_receipt,
    ).exclude(pk=voucher.pk).exists():
        raise LoyaltyBlocked("Referência de resgate já utilizada.")
    if voucher.unit == LoyaltyVoucher.Unit.POINTS:
        for allocation in VoucherPointAllocation.objects.filter(voucher=voucher):
            transition_points(
                lot_id=allocation.lot_id, kind=PointEvent.Kind.REDEEM,
                amount=allocation.amount,
                idempotency_key=f"voucher:{voucher.pk}:redeem:{allocation.lot_id}",
                external_receipt=external_receipt,
            )
    else:
        append_cashback_event(
            participant=voucher.participant, kind=CashbackEvent.Kind.REDEEM,
            amount_cents=voucher.amount,
            idempotency_key=f"voucher:{voucher.pk}:redeem",
            source_order_id=external_receipt, rule_version=f"rule:{voucher.rule.version}",
        )
    voucher.state = LoyaltyVoucher.State.REDEEMED
    voucher.redeemed_at = timezone.now()
    voucher.redemption_channel = channel
    voucher.redemption_reference = external_receipt
    voucher.save(update_fields=[
        "state", "redeemed_at", "redemption_channel", "redemption_reference",
    ])
    return voucher, True


@transaction.atomic
def reverse_grant(*, grant_id, refund_evidence_id):
    """Estorna saldo efetivo; quando já consumido, registra recuperação explícita.

    Nunca debita saldo negativo nem assume que uma venda com status refunded
    representa um estorno PSP. Prova de estorno separada é obrigatória.
    """
    _execution_enabled()
    base = LoyaltyGrant.objects.get(pk=grant_id)
    tenant = Tenant.objects.select_for_update().get(pk=base.tenant_id, status=Tenant.Status.ACTIVE)
    grant = LoyaltyGrant.objects.select_for_update().select_related(
        "sale", "participant", "rule", "point_lot", "cashback_event",
    ).get(pk=grant_id, tenant=tenant)
    if grant.status in (LoyaltyGrant.Status.REVERSED, LoyaltyGrant.Status.RECOVERY):
        linked = LoyaltyRecovery.objects.filter(grant=grant).first()
        if linked and linked.evidence_id != refund_evidence_id:
            raise LoyaltyBlocked("Estorno já registrado com outra evidência.")
        return grant, False
    if grant.sale.order_status not in (
        SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED,
    ):
        raise LoyaltyBlocked("Venda ainda não cancelada/estornada.")
    proof = FinancialEvidence.objects.get(pk=refund_evidence_id)
    _evidence(
        proof, kind=FinancialEvidence.Kind.REFUND,
        sale=grant.sale, amount=grant.eligible_amount_cents,
    )
    if proof.occurred_at < grant.captured_at:
        raise LoyaltyBlocked("Estorno anterior à captura.")
    # Reservas ainda não usadas são canceladas para liberar o crédito
    # antes da reversão. Vouchers já resgatados NÃO são desfeitos.
    vouchers = LoyaltyVoucher.objects.select_for_update().filter(
        tenant=tenant, participant=grant.participant,
        state=LoyaltyVoucher.State.RESERVED,
    )
    for voucher in vouchers:
        _cancel_reserved_voucher(voucher)
    missing_points = 0
    missing_cashback = 0
    if grant.point_lot_id:
        lot = grant.point_lot
        balances = lot_balances(lot)
        for bucket, kind in (
            ("pending", PointEvent.Kind.REVERSE_PENDING),
            ("available", PointEvent.Kind.REVERSE_AVAILABLE),
        ):
            if balances[bucket]:
                transition_points(
                    lot_id=lot.pk, kind=kind, amount=balances[bucket],
                    idempotency_key=f"grant:{grant.pk}:refund:{bucket}",
                )
        # Consumo já realizado não pode ser debitado do lote novamente.
        missing_points = PointEvent.objects.filter(
            lot=lot, kind=PointEvent.Kind.REDEEM,
        ).aggregate(total=Sum("amount"))["total"] or 0
    if grant.cashback_event_id:
        balance = cashback_wallet_balances(grant.cashback_event.wallet)
        remaining = grant.cashback_cents
        for bucket, kind in (
            ("pending_cents", CashbackEvent.Kind.REVERSE_PENDING),
            ("available_cents", CashbackEvent.Kind.REVERSE_AVAILABLE),
        ):
            take = min(remaining, balance[bucket])
            if take:
                append_cashback_event(
                    participant=grant.participant, kind=kind, amount_cents=take,
                    idempotency_key=f"grant:{grant.pk}:refund:{bucket}",
                    source_order_id=str(grant.sale_id), rule_version=f"rule:{grant.rule.version}",
                )
                remaining -= take
        missing_cashback = remaining
    grant.status = (
        LoyaltyGrant.Status.RECOVERY if missing_points or missing_cashback
        else LoyaltyGrant.Status.REVERSED
    )
    grant.reversed_at = timezone.now()
    grant.save(update_fields=["status", "reversed_at"])
    # Sempre registra a evidência da reversão, mesmo quando recuperado 100%.
    LoyaltyRecovery.objects.create(
        grant=grant, evidence=proof, remaining_points=missing_points,
        remaining_cashback_cents=missing_cashback,
        resolved_at=None if missing_points or missing_cashback else timezone.now(),
    )
    _update_tier(
        tenant=tenant, participant=grant.participant, rule=grant.rule,
        now=timezone.now(),
    )
    return grant, True



@transaction.atomic
def record_engagement_eligibility(*, participant_id, kind, now=None):
    """Missão verificada é evento de elegibilidade; NÃO emite pontos falsos.

    Fluxo futuro terá regras de eventos não transacionais no ledger e
    verificação antifraude. Não criar PointLot como se missão fosse compra.
    """
    if kind not in (LoyaltyEngagement.Kind.PROFILE, LoyaltyEngagement.Kind.BIRTHDAY):
        raise LoyaltyBlocked("Missão inválida.")
    now = now or timezone.now()
    participant = ProgramParticipant.objects.select_related("customer_profile").get(
        pk=participant_id, status=ProgramParticipant.Status.ACTIVE,
    )
    tenant = Tenant.objects.select_for_update().get(
        pk=participant.tenant_id, status=Tenant.Status.ACTIVE,
    )
    profile = getattr(participant, "customer_profile", None)
    if not profile or profile.tenant_id != tenant.pk:
        raise LoyaltyBlocked("Perfil verificado obrigatório.")
    proven = set(profile.verified_contacts.values_list("kind", flat=True))
    if proven != {"email", "phone"}:
        raise LoyaltyBlocked("Telefone e e-mail ainda não foram confirmados.")
    if not (
        profile.birth_date and profile.birth_date_consent_at and profile.birth_date_verified_at
        and profile.birth_date_verified_at <= now
    ):
        raise LoyaltyBlocked("Nascimento não confirmado com consentimento.")
    if kind == LoyaltyEngagement.Kind.BIRTHDAY:
        if (profile.birth_date.month, profile.birth_date.day) != (now.month, now.day):
            raise LoyaltyBlocked("Fora da data de aniversário.")
        period = str(now.year)
    else:
        period = "once"
    event, created = LoyaltyEngagement.objects.get_or_create(
        tenant=tenant, participant=participant, kind=kind,
        period_key=period, defaults={"eligible_at": now},
    )
    return event, created
