"""Short-lived, OTP-session-bound coupon eligibility checks for NubeSDK QA.

The checkout email is NOT proof of identity. The signed bearer is issued
ONLY after the member portal email-link session was verified. Browser-side
cart:validate can still be bypassed; it is never a commercial security gate.
"""
import hashlib
import re
import secrets
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customers.services import find_verified_customer, normalize_email
from apps.nuvemshop.models import NuvemshopCouponIntent
from apps.participants.member_portal_views import (
    _authorized_submission, _participant, _tenant,
)
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant

SALT = "vidalys.checkout-eligibility-token.v1"
NONCE_TTL_SECONDS = 180
MAX_TOKEN_AGE_SECONDS = 120
COUPON_RE = re.compile(r"^VF[A-Za-z0-9_-]{8,78}$")


def _private(data, status=200):
    response = Response(data, status=status)
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _nonce_key(nonce):
    return "checkout:nonce:" + salted_hmac(
        "vidalys.checkout-elig-nonce", nonce,
        secret=settings.SECRET_KEY,
    ).hexdigest()


def _limit(request, tenant_key):
    # Proxy-injected IP headers are intentionally ignored. Behind a trusted
    # reverse proxy configure REMOTE_ADDR to the actual client address.
    ip = request.META.get("REMOTE_ADDR", "")
    digest = salted_hmac(
        "vidalys.checkout-elig-rate", tenant_key + ":" + ip,
        secret=settings.SECRET_KEY,
    ).hexdigest()
    key = "checkout:rate:" + digest
    try:
        cache.add(key, 0, timeout=60)
        return cache.incr(key) <= 12
    except (ValueError, TypeError, ConnectionError, OSError):
        return False


def _allowed_origin(origin):
    if not isinstance(origin,str) or not origin.startswith("https://"):
        return False
    configured = getattr(settings, "FIDELIZA_CHECKOUT_ALLOWED_ORIGINS", ())
    return origin in configured


@method_decorator(csrf_protect, name="dispatch")
class IssueCheckoutEligibilityTokenView(APIView):
    """One narrow token issued to an active, verified member portal session."""
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request, slug):
        tenant = _tenant(slug)
        submission = _authorized_submission(request, tenant)
        participant = _participant(submission) if submission is not None else None
        if (participant is None
                or participant.status != ProgramParticipant.Status.ACTIVE
                or not participant.customer_profile.verified_contacts.filter(
                    kind="email", proof_method="email_otp",
                ).exists()):
            return _private({"issued": False}, status=403)
        if not _limit(request, str(tenant.pk)):
            return _private({"issued": False}, status=429)
        nonce = secrets.token_urlsafe(24)
        cache_key = _nonce_key(nonce)
        try:
            created = cache.add(
                cache_key, str(participant.pk), timeout=NONCE_TTL_SECONDS,
            )
        except (ValueError, TypeError, ConnectionError, OSError):
            return _private({"issued": False}, status=503)
        if not created:
            return _private({"issued": False}, status=503)
        token = signing.dumps({
            "tenant_id": str(tenant.pk),
            "participant_id": str(participant.pk),
            "store_id": tenant.external_store_id,
            "nonce": nonce,
        }, salt=SALT)
        return _private({
            "issued": True, "token": token, "expires_in": MAX_TOKEN_AGE_SECONDS,
        })


class PublicCouponEligibilityView(APIView):
    """Boolean response only; never look up a holder by client email alone."""
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def options(self, request):
        origin = request.headers.get("Origin")
        response = _private({"eligible": False}, status=200)
        if _allowed_origin(origin):
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type"
            response["Vary"] = "Origin"
        return response

    def post(self, request):
        origin = request.headers.get("Origin")
        if origin and not _allowed_origin(origin):
            return _private({"eligible": False}, status=403)
        data = request.data
        if (not isinstance(data,dict) or set(data) !=
                {"store_id", "code", "email", "identity_token"}):
            return _private({"eligible": False})
        store_id, code, email, bearer = (
            data["store_id"], data["code"], data["email"],
            data["identity_token"],
        )
        if (not isinstance(store_id, (str,int))
                or isinstance(store_id,bool)
                or not isinstance(code,str)
                or not COUPON_RE.fullmatch(code)
                or not isinstance(email,str) or len(email) > 254
                or not isinstance(bearer,str) or len(bearer) > 1200):
            return _private({"eligible": False})
        if not _limit(request, str(store_id)):
            return _private({"eligible": False}, status=429)
        try:
            claims = signing.loads(
                bearer,salt=SALT,max_age=MAX_TOKEN_AGE_SECONDS,
            )
        except (signing.BadSignature, signing.SignatureExpired, ValueError):
            return _private({"eligible": False})
        if (not isinstance(claims,dict) or str(claims.get("store_id")) != str(store_id)
                or not isinstance(claims.get("nonce"),str)
                or len(claims["nonce"]) > 80):
            return _private({"eligible": False})
        try:
            cached = cache.get(_nonce_key(claims["nonce"]))
        except (ValueError, TypeError, ConnectionError, OSError):
            return _private({"eligible": False}, status=503)
        if cached is None or cached != claims.get("participant_id"):
            return _private({"eligible": False})
        tenant = Tenant.objects.filter(
            pk=claims.get("tenant_id"),external_store_id=str(store_id),
            status=Tenant.Status.ACTIVE,
        ).first()
        if not tenant or tenant.platform != "nuvemshop":
            return _private({"eligible": False})
        try:
            profile = find_verified_customer(
                tenant_id=tenant.pk,email=normalize_email(email),
            )
        except ValueError:
            return _private({"eligible": False})
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        intent = NuvemshopCouponIntent.objects.select_related(
            "voucher",
        ).filter(
            tenant=tenant,store_id=str(store_id),
            code_sha256=digest,
            state=NuvemshopCouponIntent.State.ISSUED,
        ).first()
        eligible = bool(
            profile and intent
            and str(profile.participant_id) == claims["participant_id"]
            and intent.voucher.participant_id == profile.participant_id
        )
        response = _private({"eligible": eligible})
        if _allowed_origin(origin):
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
        return response
