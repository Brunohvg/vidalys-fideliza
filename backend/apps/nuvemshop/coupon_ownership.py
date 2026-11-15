"""Fail-closed detection of coupon owner mismatch in authenticated Order GET.

This is POST-checkout detection, NOT authorization to apply a discount at
checkout. It must never set the preventive checkout verification gate.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.customers.models import CustomerProfile, ChannelCustomerReference
from apps.customers.services import (
    find_verified_customer, normalize_email, normalize_checkout_phone, normalize_cpf,
)
from apps.tenants.models import Tenant
from .models import NuvemshopCouponIntent, NuvemshopCouponOwnershipIncident
from .order_readonly import safe_id
from .security import config, decrypt_token


def _coupon_intent(*, tenant, store_id, order):
    """An exact provider coupon ID suffices to treat a checkout as suspect.

    Missing/mismatched coupon details must not cause an early return that
    lets a grant bypass ownership checks.
    """
    remote = safe_id(order.get("coupon_id"))
    if remote is None:
        return None
    return NuvemshopCouponIntent.objects.select_related("voucher").filter(
        tenant=tenant, store_id=store_id, remote_coupon_id=remote,
    ).first()


def _code_matches(order, intent, cfg):
    items = order.get("coupon")
    if not isinstance(items, list):
        return False
    codes = [item.get("code") for item in items
             if isinstance(item, dict)
             and safe_id(item.get("id")) == intent.remote_coupon_id]
    return (len(codes) == 1 and isinstance(codes[0], str) and
            codes[0] == decrypt_token(intent.encrypted_code, cfg.token_keys))


def _ownership_matches(*, order, intent):
    profile = CustomerProfile.objects.filter(
        tenant_id=intent.tenant_id,
        participant_id=intent.voucher.participant_id,
    ).first()
    if profile is None:
        return False
    buyer = order.get("customer") if isinstance(order.get("customer"),dict) else {}
    contact_fields = (
        (order.get("contact_email"),normalize_email,"email"),
        (buyer.get("email"),normalize_email,"email"),
        (order.get("contact_phone"),normalize_checkout_phone,"phone_e164"),
        (buyer.get("phone"),normalize_checkout_phone,"phone_e164"),
        (order.get("contact_identification"),normalize_cpf,"cpf"),
    )
    verified = 0
    for raw, normalize, argument in contact_fields:
        if raw in (None,""):
            continue
        if not isinstance(raw,str):
            return False
        try:
            normalized = normalize(raw)
            match = find_verified_customer(
                tenant_id=intent.tenant_id, **{argument:normalized}
            )
        except ValueError:
            return False
        if match is None or match.pk != profile.pk:
            return False
        verified += 1
    customer_id = safe_id(buyer.get("id"))
    if customer_id:
        known = ChannelCustomerReference.objects.filter(
            tenant_id=intent.tenant_id, channel="nuvemshop",
            external_id=customer_id,
        ).first()
        if known and known.profile_id != profile.pk:
            return False
        if profile.channel_references.filter(channel="nuvemshop").exists():
            if known is None:
                return False
    return verified > 0


def check_paid_coupon_ownership(*, event, order, cfg=None):
    """Must run AFTER OAuth identity/store/order verification, BEFORE ingestion.

    Only a matching coupon belonging to this application is inspected.
    A violation reserves points and blocks issuance until reviewed; no PII.
    """
    if (order.get("payment_status") != "paid"
            or order.get("status") == "cancelled"):
        return None
    intent = _coupon_intent(
        tenant=event.tenant, store_id=event.store_id, order=order,
    )
    if intent is None:
        return None
    if intent.state == intent.State.OWNERSHIP_VIOLATION:
        return "ownership_violation"
    if intent.state == intent.State.SETTLED:
        return "already_settled"
    if intent.state not in (intent.State.ISSUED,intent.State.APPLIED):
        return None
    integrity = _code_matches(order, intent, cfg or config())
    if integrity and _ownership_matches(order=order,intent=intent):
        return None

    # This is a SECURITY event, not a refund nor proof of PSP capture.
    with transaction.atomic():
        Tenant.objects.select_for_update().get(pk=event.tenant_id)
        locked = NuvemshopCouponIntent.objects.select_for_update().get(pk=intent.pk)
        if locked.state == locked.State.SETTLED:
            return "already_settled"
        if locked.state not in (locked.State.ISSUED,locked.State.APPLIED,
                                locked.State.OWNERSHIP_VIOLATION):
            return None
        if locked.order_id and locked.order_id != event.order_id:
            return "requires_review"
        locked.order_id = event.order_id
        locked.state = locked.State.OWNERSHIP_VIOLATION
        locked.save(update_fields=["order_id","state","updated_at"])
        digest = salted_hmac(
            "vidalys.coupon-ownership-incident.v1",
            str(event.tenant_id)+":"+event.store_id+":"+event.order_id,
            secret=settings.SECRET_KEY, algorithm="sha256",
        ).hexdigest()
        NuvemshopCouponOwnershipIncident.objects.get_or_create(
            intent=locked,
            defaults={"tenant_id":event.tenant_id,"order_digest":digest,
                      "reason":("identity_mismatch" if integrity
                                else "coupon_details_mismatch")},
        )
    return "ownership_violation"
