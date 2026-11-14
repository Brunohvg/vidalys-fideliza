"""Ingestão transacional sem lançamento financeiro ou suposição de pagamento.

Identidades autodeclaradas só fazem match em contato previamente verificado.
Se não existir contato comprovado, cria perfil PROVISÓRIO por pedido.
Uma correspondência de contato em evento de venda não equivale a OTP do comprador.
"""
import hashlib
import json
import re
import secrets
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.customers.models import CustomerProfile
from apps.customers.services import _digests, find_verified_customer
from apps.sales.models import SaleEventReceipt, SaleRecord
from apps.tenants.models import Tenant

from .models import ChannelCredential


AUTH_HEADER = re.compile(r"^vf_([0-9a-f]{32})\.([A-Za-z0-9_-]{55,80})$")
NEXT_STATUS = {
    SaleRecord.OrderStatus.PENDING: {
        SaleRecord.OrderStatus.PAID, SaleRecord.OrderStatus.CANCELLED,
    },
    SaleRecord.OrderStatus.PAID: {
        SaleRecord.OrderStatus.REFUNDED, SaleRecord.OrderStatus.CANCELLED,
    },
    SaleRecord.OrderStatus.CANCELLED: set(),
    SaleRecord.OrderStatus.REFUNDED: set(),
}


class IngestionConflict(ValueError):
    """Reenvio com outro conteúdo, referência legada ou identidade divergente."""


@dataclass(frozen=True)
class IngestionResult:
    sale: SaleRecord
    event: SaleEventReceipt
    created: bool
    duplicate: bool
    identity_status: str


def issue_flow_key(*, tenant_id, label, expires_at=None):
    """Uso interno por operador autorizado; retorna segredo SOMENTE nesta chamada."""
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
        raise ValueError("Identifique a credencial.")
    tenant = Tenant.objects.get(pk=tenant_id, status=Tenant.Status.ACTIVE)
    if expires_at is not None and (not timezone.is_aware(expires_at) or expires_at <= timezone.now()):
        raise ValueError("Validade inválida.")
    secret = secrets.token_urlsafe(48)
    row = ChannelCredential.objects.create(
        tenant=tenant, channel=ChannelCredential.Channel.VIDALYS_FLOW,
        label=label.strip(), key_hash=make_password(secret), expires_at=expires_at,
    )
    return row, f"vf_{row.pk.hex}.{secret}"


def authenticate_flow_key(*, tenant_id, authorization):
    """Credencial do Flow nunca autoriza outro tenant/canal."""
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    matched = AUTH_HEADER.fullmatch(token)
    if not matched:
        return None
    try:
        credential_id = uuid.UUID(hex=matched.group(1))
        credential = ChannelCredential.objects.select_related("tenant").get(
            pk=credential_id, tenant_id=tenant_id,
            channel=ChannelCredential.Channel.VIDALYS_FLOW,
            revoked_at__isnull=True, tenant__status=Tenant.Status.ACTIVE,
        )
    except (ValueError, ChannelCredential.DoesNotExist):
        return None
    if credential.expires_at and credential.expires_at <= timezone.now():
        return None
    if not check_password(matched.group(2), credential.key_hash):
        return None
    return credential


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_key(*, tenant_id, channel, order_id, event_id, status):
    # A identidade do PEDIDO não muda a cada status. A do EVENTO sim.
    suffix = "event:" + event_id if event_id else "status:" + status
    return _hash(json.dumps([str(tenant_id), channel, order_id, suffix], separators=(",", ":")))


def _payload_digests(data):
    # HMAC: não persistir telefone/e-mail nem hash simples sujeito a dicionário.
    canonical = json.dumps([
        str(data["tenant_id"]), data["channel"], data["external_order_id"],
        data["customer_identifier"], data["total_amount"], data["currency"],
        data["status"], data.get("source_event_id", ""),
        data["occurred_at"].isoformat() if data.get("occurred_at") else "",
    ], separators=(",", ":"), ensure_ascii=True)
    secrets = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return tuple(dict.fromkeys(
        salted_hmac(
            "vidalys.sales-event.v1", canonical, secret=secret,
            algorithm="sha256",
        ).hexdigest()
        for secret in secrets
    ))


def _order_key(data):
    return _hash(json.dumps([
        str(data["tenant_id"]), data["channel"], data["external_order_id"],
    ], separators=(",", ":")))


def _contact_digests(*, tenant_id, value):
    kind = "email" if "@" in value else "phone"
    return _digests(tenant_id=tenant_id, kind=kind, value=value)


@transaction.atomic
def ingest_order_event(*, data, actor=None):
    """Persiste notificação, mas NÃO chama services de points ou wallets."""
    tenant = Tenant.objects.select_for_update().get(
        pk=data["tenant_id"], status=Tenant.Status.ACTIVE,
    )
    channel = data["channel"]
    order_ref = data["external_order_id"]
    source_event_id = data.get("source_event_id", "")
    event_key = _event_key(
        tenant_id=tenant.pk, channel=channel, order_id=order_ref,
        event_id=source_event_id, status=data["status"],
    )
    digests = _payload_digests(data)
    existing_event = SaleEventReceipt.objects.select_related("sale").filter(
        idempotency_key=event_key,
    ).first()
    if existing_event:
        if existing_event.payload_digest not in digests:
            raise IngestionConflict("Reenvio com chave de evento e conteúdo divergentes.")
        return IngestionResult(
            sale=existing_event.sale, event=existing_event,
            created=False, duplicate=True,
            identity_status="already_recorded",
        )
    if source_event_id and SaleEventReceipt.objects.filter(
        tenant=tenant, channel=channel, source_event_id=source_event_id,
    ).exists():
        raise IngestionConflict("ID do evento já usado em outra venda.")

    sale = SaleRecord.objects.select_related("customer_profile").filter(
        tenant=tenant, channel=channel, external_reference=order_ref,
    ).first()
    order_key = _order_key(data)
    matched = find_verified_customer(
        tenant_id=tenant.pk,
        **({"email": data["customer_identifier"]} if "@" in data["customer_identifier"]
           else {"phone_e164": data["customer_identifier"]}),
    )
    identity_status = "verified_contact_match" if matched else "provisional"
    digests = _contact_digests(tenant_id=tenant.pk, value=data["customer_identifier"])
    occurred = data.get("occurred_at")
    now = timezone.now()
    effective_at = occurred or now
    created = sale is None
    applied = True

    if sale is None:
        profile = matched or CustomerProfile.objects.create(tenant=tenant)
        sale = SaleRecord.objects.create(
            tenant=tenant, channel=channel, external_reference=order_ref,
            source_order_key=order_key, customer_profile=profile,
            reported_contact_digest=digests[0],
            reported_total_cents=data["total_amount"],
            eligible_amount_cents=0, currency="BRL",
            order_status=data["status"], status_changed_at=effective_at,
            # Relato do canal não comprova pagamento; sem data não inventar.
            reported_paid_at=occurred if data["status"] == SaleRecord.OrderStatus.PAID else None,
            evidence_reference="",
            state=(
                SaleRecord.State.AWAITING_REVIEW
                if channel == SaleRecord.Channel.COUNTER
                and matched and matched.participant_id
                and data["status"] == SaleRecord.OrderStatus.PAID
                else SaleRecord.State.AWAITING_MEMBER
            ),
            participant=(
                matched.participant if channel == SaleRecord.Channel.COUNTER
                and matched and matched.participant_id
                and data["status"] == SaleRecord.OrderStatus.PAID else None
            ),
            submitted_by=actor if channel == SaleRecord.Channel.COUNTER else None,
        )
    else:
        if not sale.source_order_key or sale.source_order_key != order_key:
            raise IngestionConflict("Venda existente criada por fluxo legado; conciliação necessária.")
        if sale.reported_contact_digest not in digests:
            raise IngestionConflict("Cliente informado diverge do pedido já registrado.")
        if sale.reported_total_cents != data["total_amount"]:
            raise IngestionConflict("Valor diferente para a mesma referência de pedido.")
        if matched and sale.customer_profile_id != matched.pk:
            raise IngestionConflict("Identidade do pedido diverge de perfil já comprovado.")
        if occurred and sale.status_changed_at and occurred < sale.status_changed_at:
            applied = False
        elif data["status"] != sale.order_status and data["status"] not in NEXT_STATUS[sale.order_status]:
            applied = False
        if applied and data["status"] != sale.order_status:
            sale.order_status = data["status"]
            sale.status_changed_at = effective_at
            if data["status"] == SaleRecord.OrderStatus.PAID:
                sale.reported_paid_at = occurred  # nunca marca pago como conciliado
            sale.save(update_fields=["order_status", "status_changed_at", "reported_paid_at"])

    receipt = SaleEventReceipt.objects.create(
        tenant=tenant, sale=sale, channel=channel, source_event_id=source_event_id,
        idempotency_key=event_key, payload_digest=digests[0],
        reported_status=data["status"], reported_total_cents=data["total_amount"],
        outcome=SaleEventReceipt.Outcome.APPLIED if applied else SaleEventReceipt.Outcome.IGNORED,
        occurred_at=occurred,
    )
    return IngestionResult(
        sale=sale, event=receipt, created=created, duplicate=False,
        identity_status=identity_status,
    )
