"""Homolog API smoke. Synthetic records roll back; no SMTP/OAuth calls.

Uses Django TestClient internally; validate public HTTPS separately.
PostgreSQL execution requires FIDELIZA_SMOKE_HOMOLOG=1 and the exact homolog DB."""
import hashlib
import os
import sys
import uuid
from datetime import timedelta

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.test import Client
from django.utils import timezone
from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.branding_models import TenantBranding, TenantBrandingAudit
from apps.participants.models import ProgramParticipant
from apps.participants.enrollment_models import (
    ProgramTerms, EnrollmentInvite, EnrollmentSubmission, EnrollmentEmailChallenge,
)
from apps.participants.email_proof import make_token, digest
from apps.wallets.services import append_cashback_event

if connection.settings_dict["NAME"] == ":memory:":
    call_command("migrate", verbosity=0)
else:
    expected_db = (
        os.getenv("FIDELIZA_SMOKE_HOMOLOG") == "1"
        and connection.vendor == "postgresql"
        and connection.settings_dict["NAME"] == "fideliza_homolog"
        and connection.settings_dict["HOST"] == "zdssuoxsh4slxrcnavuoqja1"
    )
    if not expected_db:
        raise SystemExit("Smoke blocked: explicit homolog DB opt-in required.")

assert not settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED, "Public signup must be off"
assert not settings.FIDELIZA_EMAIL_DELIVERY_ENABLED, "External mail must be off"
assert not settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
assert not settings.FIDELIZA_LEDGER_WRITES_ENABLED

host = "fideliza-homolog.optarys.com.br"
origin = "https://" + host
prefix = "audit-" + uuid.uuid4().hex[:16]
User = get_user_model()

def ok(label):
    print(label + ": OK")

def client_for(user=None):
    c = Client(enforce_csrf_checks=True, HTTP_HOST=host)
    if user:
        c.force_login(user)
    assert c.get("/api/v1/auth/session/", secure=True).status_code == 200
    return c

def write(c, method, path, payload, expected, csrf=True):
    headers = {"HTTP_ORIGIN": origin}
    if csrf:
        headers["HTTP_X_CSRFTOKEN"] = c.cookies["csrftoken"].value
    response = getattr(c, method)(path, data=payload, content_type="application/json",
                                  secure=True, **headers)
    assert response.status_code == expected, (path, response.status_code, expected)
    return response

with transaction.atomic():
    owner = User.objects.create_user(username=prefix + "-owner", password=None)
    analyst = User.objects.create_user(username=prefix + "-analyst", password=None)
    own = Tenant.objects.create(name="Loja sintetica de auditoria", slug=prefix + "-a",
                                 status="active")
    other = Tenant.objects.create(name="Outra loja sintetica", slug=prefix + "-b")
    TenantMembership.objects.create(user=owner, tenant=own, role="owner")
    TenantMembership.objects.create(user=analyst, tenant=own, role="analyst")
    c = client_for(owner)
    readonly = client_for(analyst)
    anonymous = client_for()
    base = f"/api/v1/tenants/{own.pk}/"

    assert anonymous.get(base + "participants/", secure=True).status_code == 403
    assert c.get(f"/api/v1/tenants/{other.pk}/participants/", secure=True).status_code == 404
    ok("AUTH_AND_TENANT_BOUNDARIES")

    preferences = base + "settings/"
    assert anonymous.get(preferences, secure=True).status_code == 403
    assert c.get(f"/api/v1/tenants/{other.pk}/settings/", secure=True).status_code == 404
    assert c.get(preferences, secure=True).json()["version"] == 0
    branding = {"program_name": "Clube sintetico QA", "primary_color": "#087F79",
                "accent_color": "#37D5BB", "support_email": "qa@example.invalid",
                "expected_version": 0}
    write(c, "patch", preferences, branding, 403, csrf=False)
    write(readonly, "patch", preferences, branding, 403)
    saved = write(c, "patch", preferences, branding, 200).json()
    assert saved["updated"] and saved["version"] == 1
    write(c, "patch", preferences, branding, 409)
    assert TenantBranding.objects.get(tenant=own).program_name == branding["program_name"]
    assert TenantBrandingAudit.objects.filter(tenant=own).count() == 1
    prefs = c.get(preferences, secure=True).json()
    assert prefs["branding"]["program_name"] == branding["program_name"]
    assert prefs["public_link"] is None
    assert not any(prefs["features"].values())
    ok("STORE_SETTINGS_CSRF_ACL_VERSION_AND_AUDIT")

    campaign = {"title": "Rascunho sintetico QA", "goal": "second_purchase",
                "cashback_rate_bps": 200, "ticket_cents": 10000,
                "projected_paid_orders": 10, "budget_cents": 3000}
    path = base + "campaign-drafts/"
    write(c, "post", path, campaign, 403, csrf=False)
    write(readonly, "post", path, campaign, 403)
    draft = write(c, "post", path, campaign, 201).json()
    assert draft["status"] == "draft" and draft["preview"]["assumptions_only"]
    detail = path + draft["id"] + "/"
    updated = write(c, "patch", detail,
                    {**campaign, "budget_cents": 4000, "expected_version": 1}, 200).json()
    assert updated["version"] == 2
    write(c, "patch", detail, {**campaign, "expected_version": 1}, 409)
    write(c, "post", path, {**campaign, "status": "active"}, 400)
    assert c.get(path, secure=True).json()["activation_available"] is False
    ok("CAMPAIGN_SAVE_RESUME_VERSION_AND_NO_ACTIVATION")

    terms_data = {"version": "audit-v1", "title": "Termos sinteticos QA",
                  "body": "Texto sintetico apenas para auditoria. " * 5,
                  "privacy_notice": "Aviso de privacidade sintetico para auditoria. " * 5}
    write(readonly, "post", base + "program-terms/", terms_data, 403)
    terms_response = write(c, "post", base + "program-terms/", terms_data, 201).json()
    assert terms_response["public_signup_enabled"] is False
    write(c, "post", base + "enrollment-invitations/", {}, 409)
    assert anonymous.get(f"/api/v1/public/programs/{own.slug}/", secure=True).status_code == 404
    assert readonly.get(base + "enrollment-submissions/", secure=True).status_code == 403
    ok("TERMS_ACL_AND_PUBLIC_SIGNUP_GATE")

    now = timezone.now()
    terms = ProgramTerms.objects.get(pk=terms_response["terms"]["id"])
    invite = EnrollmentInvite.objects.create(
        tenant=own, terms=terms, token_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        created_by=owner, expires_at=now + timedelta(hours=1), consumed_at=now)
    submission = EnrollmentSubmission.objects.create(
        tenant=own, invitation=invite, terms=terms, name="Pessoa sintetica QA",
        email=prefix + "@example.invalid", accepted_at=now, marketing_opt_in=True,
        terms_digest=hashlib.sha256((terms.body + "\n" + terms.privacy_notice).encode()).hexdigest())

    for purpose, expected_status in [("verify", "email_verified"), ("withdraw", "withdrawn")]:
        challenge_id = uuid.uuid4()
        token = make_token(challenge_id, purpose)
        EnrollmentEmailChallenge.objects.create(
            id=challenge_id, submission=submission, purpose=purpose,
            token_digest=digest(token), expires_at=now + timedelta(minutes=30))
        payload = {"token": token, "action": purpose}
        endpoint = "/api/v1/public/enrollment/email-action/"
        write(anonymous, "post", endpoint, payload, 403, csrf=False)
        result = write(anonymous, "post", endpoint, payload, 200).json()
        assert result["status"] == expected_status
        assert result["participant_created"] is False and result["cashback_enabled"] is False
        write(anonymous, "post", endpoint, payload, 410)
        if purpose == "verify":
            write(c, "post", base + f"enrollment-submissions/{submission.pk}/customer-match/preview/", {}, 409)
    submission.refresh_from_db()
    assert submission.marketing_opt_in is False and submission.withdrawn_at
    assert ProgramParticipant.objects.filter(tenant=own).count() == 0
    ok("EMAIL_PROOF_REPLAY_WITHDRAWAL_AND_CUSTOMER_GATE")

    try:
        append_cashback_event(participant=ProgramParticipant(tenant=own), kind="accrual",
                              amount_cents=100, idempotency_key=prefix,
                              source_order_id="qa-only", rule_version="audit-v1")
    except PermissionError:
        pass
    else:
        raise AssertionError("Ledger writes must be disabled")
    ok("LEDGER_WRITES_BLOCKED")
    c.logout()
    assert c.get(base + "participants/", secure=True).status_code == 403
    transaction.set_rollback(True)

assert not User.objects.filter(username__startswith=prefix).exists()
assert not Tenant.objects.filter(slug__startswith=prefix).exists()
ok("ROLLBACK_NO_SYNTHETIC_RECORDS_LEFT")
print("STAGING_API_SMOKE_OK; NO_EXTERNAL_MAIL_OR_NUVEMSHOP_REQUESTS")
