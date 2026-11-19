"""Site (Nuvemshop): ganhar em pedido pago e resgatar por cupom único — padrão de mercado.

Ganhar: pedido pago de cliente do clube (perfil verificado ou e-mail confirmado no clube)
vira saldo pendente, sem passar por Conferir. Cancelado/estornado na carência: saldo sai.

Resgatar: a API de cupons da Nuvemshop não restringe cupom a uma cliente; por isso cada
saldo vira um código único e difícil de adivinhar, com uso máximo 1, pedido mínimo e
validade. O saldo fica RESERVADO no ledger enquanto o cupom existe:
- pedido pago com o código  -> resgate (REDEEM);
- uso no caixa, vencimento ou troca -> cupom apagado na Nuvemshop e reserva devolvida.

Chamadas à Nuvemshop precisam do token OAuth: rodam na API ou no worker isolado
(fila "nuvemshop"), nunca no worker de e-mail.
"""
import hashlib
import logging
import re
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent, PointLot, PointWallet
from apps.points.services import lot_balances, transition_points
from apps.tenants.models import Tenant

from .models import CounterPilot, OnlineCoupon, SaleRecord
from .pilot import (
    PilotBlocked, _live_lots, _rewards_qs, _terms, _used, issued_points, pilot_enabled, points_for,
    program_mode, release_due, wallet_balances,
)

logger = logging.getLogger(__name__)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O/1/I para ditar no caixa
REWARD_COUPON_DAYS = 30
ACTIVE = (OnlineCoupon.State.ISSUING, OnlineCoupon.State.ISSUED)


class CouponUnavailable(ValueError):
    pass


# ---------- Prontidão ----------

def site_status(tenant):
    """O que falta para o site funcionar — mostrado ao lojista em linguagem simples."""
    from apps.nuvemshop.models import NuvemshopInstallation
    from apps.nuvemshop.scopes import parse_scopes
    installed = NuvemshopInstallation.objects.filter(tenant=tenant).first() if tenant.platform == "nuvemshop" else None
    scopes = parse_scopes(installed.scope) if installed else frozenset()
    checks = {
        "connected": installed is not None,
        "orders_scope": bool({"read_orders", "write_orders"} & scopes),
        "coupons_scope": "write_coupons" in scopes,
        "webhooks": bool(getattr(settings, "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", False)
                         and getattr(settings, "FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED", False)
                         and getattr(settings, "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", False)),
        "coupons_server": bool(getattr(settings, "FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED", False)),
    }
    checks["earning_ready"] = checks["connected"] and checks["orders_scope"] and checks["webhooks"]
    checks["coupons_ready"] = checks["earning_ready"] and checks["coupons_scope"] and checks["coupons_server"]
    return checks


def coupons_live(tenant):
    pilot = CounterPilot.objects.filter(tenant=tenant).first()
    return bool(pilot and pilot.active and pilot.online_coupons and not pilot.coupons_paused
                and site_status(tenant)["coupons_ready"])


def new_code(tenant):
    prefix = re.sub(r"[^A-Z0-9]", "", tenant.slug.upper())[:6] or "CLUBE"
    for _ in range(5):
        code = f"{prefix}-{''.join(secrets.choice(ALPHABET) for _ in range(8))}"
        if not OnlineCoupon.objects.filter(code=code).exists():
            return code
    raise CouponUnavailable("Não foi possível gerar um código único.")


# ---------- Nuvemshop (token só aqui) ----------

def _remote(tenant):
    from apps.nuvemshop.models import NuvemshopInstallation
    from apps.nuvemshop.security import config, decrypt_token
    cfg = config()
    installed = NuvemshopInstallation.objects.get(tenant=tenant, client_id=cfg.client_id)
    return installed.store_id, decrypt_token(installed.token_ciphertext, cfg.token_keys), cfg.user_agent


def remote_payload(coupon):
    until = coupon.expires_at.astimezone(timezone.utc)
    return {
        "code": coupon.code, "type": "absolute",
        "value": f"{Decimal(coupon.discount_cents) / 100:.2f}",
        "max_uses": 1, "min_price": f"{Decimal(coupon.min_order_cents) / 100:.2f}",
        "includes_shipping": False, "combines_with_other_discounts": coupon.combines,
        "end_date": until.strftime("%Y-%m-%d"), "end_time": until.strftime("%H:%M"),
    }


def _create_remote(coupon, opener=None):
    from apps.nuvemshop.coupon_client import CouponRemoteError, _transport
    from apps.nuvemshop.order_readonly import safe_id
    store_id, token, agent = _remote(coupon.tenant)
    remote = _transport(store_id=store_id, token=token, agent=agent, method="POST",
                        path="coupons", payload=remote_payload(coupon), opener=opener)
    if not isinstance(remote, dict) or safe_id(remote.get("id")) is None or remote.get("code") != coupon.code:
        raise CouponRemoteError("Cupom criado com dados divergentes")
    url = ""
    try:
        store = _transport(store_id=store_id, token=token, agent=agent, method="GET",
                           path="store?fields=url_with_protocol", opener=opener)
        base = store.get("url_with_protocol") if isinstance(store, dict) else ""
        if isinstance(base, str) and base.startswith("https://") and len(base) < 200:
            url = base.rstrip("/") + "/discount/" + coupon.code
    except CouponRemoteError:
        url = ""
    return str(remote["id"]), url


def _delete_remote(coupon, opener=None):
    from apps.nuvemshop.coupon_client import delete_coupon_once, inspect_coupon_by_id
    if not coupon.remote_id:
        return True
    store_id, token, agent = _remote(coupon.tenant)
    try:
        return delete_coupon_once(store_id=store_id, token=token, agent=agent,
                                  remote_id=coupon.remote_id, opener=opener)
    except Exception:
        # Exclusão incerta: só aceitamos se a reconsulta mostrar que o cupom não existe.
        if inspect_coupon_by_id(store_id=store_id, token=token, agent=agent,
                                remote_id=coupon.remote_id, opener=opener) is None:
            return True
        raise


# ---------- Reserva no ledger ----------

def _reserve(coupon, wallet, amount):
    remaining, allocations = amount, []
    for lot in _live_lots(wallet):
        if remaining == 0:
            break
        take = min(lot_balances(lot)["available"], remaining)
        if take <= 0:
            continue
        transition_points(lot_id=lot.pk, kind=PointEvent.Kind.RESERVE, amount=take,
                          idempotency_key=f"coupon-reserve:{coupon.pk}")
        allocations.append({"lot": str(lot.pk), "amount": take})
        remaining -= take
    if remaining:
        raise CouponUnavailable("Saldo mudou durante a operação.")
    return allocations


def _release_reserve(coupon, *, redeem, order_id=""):
    kind = PointEvent.Kind.REDEEM if redeem else PointEvent.Kind.CANCEL_RESERVE
    key = f"coupon-{'redeem' if redeem else 'cancel'}:{coupon.pk}"
    for item in coupon.allocations:
        transition_points(lot_id=item["lot"], kind=kind, amount=item["amount"], idempotency_key=key,
                          external_receipt=f"site:{order_id}:{coupon.code}" if redeem else "")


def active_coupon(participant, source=None):
    qs = OnlineCoupon.objects.filter(participant=participant, state__in=ACTIVE)
    return (qs.filter(source=source) if source else qs).order_by("-created_at").first()


def issue_coupon(participant, *, reward_id=None, opener=None):
    """Cria o cupom único. Giftback: todo o crédito liberado. Pontos: a recompensa escolhida."""
    tenant = participant.tenant
    if not pilot_enabled(tenant) or not coupons_live(tenant):
        raise CouponUnavailable("Resgate pelo site está desligado nesta loja.")
    pilot = CounterPilot.objects.get(tenant=tenant)
    gift = program_mode(tenant.pk)
    wallet = PointWallet.objects.filter(participant=participant, tenant=tenant).first()
    if wallet is None:
        raise CouponUnavailable("Ainda não há saldo para gerar cupom.")
    with transaction.atomic():
        ProgramParticipant.objects.select_for_update().get(pk=participant.pk)
        release_due(wallet)
        _, totals = wallet_balances(participant)
        if gift:
            if reward_id is not None:
                raise CouponUnavailable("No giftback, o cupom usa todo o crédito.")
            amount = totals["available"]
            if amount <= 0:
                raise CouponUnavailable("Ainda não há crédito liberado.")
            lots = [lot for lot in _live_lots(wallet) if lot_balances(lot)["available"] > 0]
            expires = min(lot.expires_at for lot in lots)
            discount, minimum, reward, source = amount, gift.giftback_min_order_cents, None, OnlineCoupon.Source.GIFTBACK
            minimum = max(minimum, discount + 1)
        else:
            reward = _rewards_qs(tenant.pk).filter(pk=reward_id).first() if reward_id else None
            if reward is None or "nuvemshop" not in (reward.allowed_channels or ""):
                raise CouponUnavailable("Esta recompensa não pode ser usada no site.")
            if _used(reward) + OnlineCoupon.objects.filter(reward=reward).exclude(
                    state__in=(OnlineCoupon.State.CANCELLED, OnlineCoupon.State.EXPIRED,
                               OnlineCoupon.State.FAILED)).count() >= reward.max_redemptions:
                raise CouponUnavailable("Esta recompensa atingiu o limite de usos.")
            amount = reward.points_cost
            if totals["available"] < amount:
                raise CouponUnavailable("Pontos liberados insuficientes para esta recompensa.")
            discount, reward_min = reward.discount_cents, reward.min_order_cents
            minimum, source = max(reward_min, discount + 1), OnlineCoupon.Source.REWARD
            expires = timezone.now() + timedelta(days=REWARD_COUPON_DAYS)
        coupon = OnlineCoupon.objects.create(
            tenant=tenant, participant=participant, source=source, reward=reward, code=new_code(tenant),
            points=amount, discount_cents=discount, min_order_cents=minimum, combines=pilot.coupon_combines,
            expires_at=expires,
        )
        coupon.allocations = _reserve(coupon, wallet, amount)
        coupon.save(update_fields=["allocations"])
    try:
        remote_id, url = _create_remote(coupon, opener=opener)
    except Exception:
        with transaction.atomic():
            _release_reserve(coupon, redeem=False)
            coupon.state = OnlineCoupon.State.FAILED
            coupon.settled_at = timezone.now()
            coupon.save(update_fields=["state", "settled_at"])
        logger.warning("online_coupon create_failed tenant=%s", tenant.pk)
        raise CouponUnavailable("A Nuvemshop não confirmou o cupom agora. Tente de novo em alguns minutos.")
    coupon.remote_id, coupon.apply_url, coupon.state = remote_id, url, OnlineCoupon.State.ISSUED
    coupon.save(update_fields=["remote_id", "apply_url", "state"])
    return coupon


def revoke_coupon(coupon, *, state=OnlineCoupon.State.CANCELLED, opener=None):
    """Apaga na Nuvemshop e devolve a reserva. Falha remota mantém tudo como está."""
    with transaction.atomic():
        coupon = OnlineCoupon.objects.select_for_update().get(pk=coupon.pk)
        if coupon.state not in ACTIVE:
            return coupon
        _delete_remote(coupon, opener=opener)
        _release_reserve(coupon, redeem=False)
        coupon.state, coupon.settled_at = state, timezone.now()
        coupon.save(update_fields=["state", "settled_at"])
    return coupon


def present_coupon(coupon):
    if coupon is None:
        return None
    return {"code": coupon.code, "discount_cents": coupon.discount_cents, "min_order_cents": coupon.min_order_cents,
            "expires_at": coupon.expires_at.isoformat(), "apply_url": coupon.apply_url, "source": coupon.source,
            "title": coupon.reward.title if coupon.reward_id else "Crédito de giftback", "state": coupon.state}


# ---------- Pedido do site (chamado pela reconsulta do webhook) ----------

def _participant_for(tenant, order, profile):
    if profile is not None and getattr(profile, "participant_id", None):
        p = ProgramParticipant.objects.filter(pk=profile.participant_id, tenant=tenant,
                                              status=ProgramParticipant.Status.ACTIVE).first()
        if p:
            return p
    from apps.participants.enrollment_models import EnrollmentSubmission
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    emails = {e.strip().lower() for e in (order.get("contact_email"), customer.get("email"))
              if isinstance(e, str) and "@" in e}
    if len(emails) != 1:
        return None
    match = list(EnrollmentSubmission.objects.filter(
        tenant=tenant, email__iexact=emails.pop(), email_verified_at__isnull=False, withdrawn_at__isnull=True,
        participant__status=ProgramParticipant.Status.ACTIVE).select_related("participant")[:2])
    return match[0].participant if len(match) == 1 else None


def _order_codes(order):
    codes = order.get("coupon")
    return {c.get("code").upper() for c in codes if isinstance(c, dict) and isinstance(c.get("code"), str)} \
        if isinstance(codes, list) else set()


def handle_order(*, tenant, order, order_id, status, total_cents, profile=None):
    """Idempotente: o mesmo pedido pode chegar várias vezes (paid/updated)."""
    if not pilot_enabled(tenant):
        return "off"
    pilot = CounterPilot.objects.get(tenant=tenant)
    result = []
    paid = status == SaleRecord.OrderStatus.PAID
    with transaction.atomic():
        if paid:
            for coupon in OnlineCoupon.objects.select_for_update().filter(
                    tenant=tenant, code__in=_order_codes(order), state=OnlineCoupon.State.ISSUED):
                _release_reserve(coupon, redeem=True, order_id=order_id)
                coupon.state, coupon.used_order_id, coupon.settled_at = OnlineCoupon.State.USED, str(order_id), timezone.now()
                coupon.save(update_fields=["state", "used_order_id", "settled_at"])
                result.append("coupon_used")
        participant = _participant_for(tenant, order, profile)
        ref = f"site:{order_id}"
        lot = PointLot.objects.filter(tenant=tenant, source_reference=ref).first()
        if participant and pilot.online_earning and paid and lot is None:
            result.append(_grant_site(tenant, participant, total_cents, ref, order_id))
        elif lot is not None and status in (SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED):
            balances = lot_balances(lot)
            if balances["pending"]:
                transition_points(lot_id=lot.pk, kind=PointEvent.Kind.REVERSE_PENDING,
                                  amount=balances["pending"], idempotency_key=f"site-reverse-p:{order_id}")
            if balances["available"]:
                transition_points(lot_id=lot.pk, kind=PointEvent.Kind.REVERSE_AVAILABLE,
                                  amount=balances["available"], idempotency_key=f"site-reverse-a:{order_id}")
            result.append("reversed")
    return ",".join(result) or "nothing"


def _grant_site(tenant, participant, total_cents, ref, order_id):
    from apps.points.services import create_pending_lot
    pilot = CounterPilot.objects.select_for_update().get(tenant=tenant)
    terms = _terms(tenant.pk)
    if terms is None:
        return "no_rule"
    hold_days, validity_days, rule_version = terms
    points, _ = points_for(tenant.pk, total_cents)
    left = pilot.budget_points - issued_points(tenant.pk)
    points = min(points, max(left, 0))
    if points <= 0:
        return "budget" if left <= 0 else "zero"
    now = timezone.now()
    paid_at = max(now - timedelta(minutes=1), participant.joined_at, participant.consent_at)
    unlock = now + timedelta(days=hold_days)
    create_pending_lot(
        participant=participant, channel=SaleRecord.Channel.NUVEMSHOP, source_reference=ref,
        eligible_amount_cents=total_cents, points=points, rule_version=rule_version, paid_at=paid_at,
        unlock_at=unlock, expires_at=unlock + timedelta(days=validity_days),
        verification_digest=hashlib.sha256(f"site|{tenant.pk}|{order_id}|{total_cents}".encode()).hexdigest(),
    )
    return "granted"


# ---------- Rotina horária (fila nuvemshop) ----------

def refresh_tenant(tenant, opener=None):
    """Vence cupons, recria o cupom de giftback quando o crédito muda e gera para quem não tem."""
    out = {"expired": 0, "issued": 0, "replaced": 0}
    now = timezone.now()
    for coupon in OnlineCoupon.objects.filter(tenant=tenant, state=OnlineCoupon.State.ISSUED, expires_at__lte=now):
        try:
            revoke_coupon(coupon, state=OnlineCoupon.State.EXPIRED, opener=opener)
            out["expired"] += 1
        except Exception:
            logger.warning("online_coupon expire_pending tenant=%s", tenant.pk)
    if not (pilot_enabled(tenant) and coupons_live(tenant) and program_mode(tenant.pk)):
        return out
    wallets = PointWallet.objects.filter(tenant=tenant, participant__status=ProgramParticipant.Status.ACTIVE)
    for wallet in wallets.select_related("participant"):
        release_due(wallet)
        _, totals = wallet_balances(wallet.participant)
        current = active_coupon(wallet.participant, OnlineCoupon.Source.GIFTBACK)
        if totals["available"] <= 0:
            continue
        try:
            if current is not None:   # crédito novo liberou: um cupom só, sempre com o total
                revoke_coupon(current, opener=opener)
                out["replaced"] += 1
            issue_coupon(wallet.participant, opener=opener)
            out["issued"] += 1
        except Exception:
            logger.warning("online_coupon refresh_failed tenant=%s", tenant.pk)
    return out


def free_for_counter(participant):
    """No caixa: devolve ao saldo o crédito preso no cupom do site (apagando o cupom)."""
    for coupon in OnlineCoupon.objects.filter(participant=participant, state__in=ACTIVE):
        try:
            revoke_coupon(coupon)
        except Exception:
            raise PilotBlocked("Não foi possível cancelar o cupom do site agora. Tente de novo em instantes.")


def refresh_all():
    tenants = Tenant.objects.filter(pk__in=CounterPilot.objects.filter(active=True).values("tenant_id"),
                                    status=Tenant.Status.ACTIVE, platform="nuvemshop")
    return {str(t.pk): refresh_tenant(t) for t in tenants}
