"""Integration smoke for disposable, isolated PostgreSQL CI only.

Intentionally DOES NOT run on any real staging/production DB. Uses temporary
synthetic users and tenants, communicates through the real Nginx -> Django path
and deletes all fixtures in a finally block. Prints no passwords or tokens.
"""
import http.client
import json
import os
import secrets
import uuid
from http.cookies import SimpleCookie

if os.environ.get("FIDELIZA_CI_ISOLATED") != "1":
    raise SystemExit("Refusing smoke test outside the explicitly isolated CI environment")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, TenantMembership

db = settings.DATABASES["default"]
if db["ENGINE"] != "django.db.backends.postgresql" or db["NAME"] != "fideliza" or db["HOST"] != "fideliza-db":
    raise SystemExit("Refusing smoke test: database is not the disposable CI PostgreSQL")

PUBLIC_HOST = "staging.invalid"
TENANT_PREFIX = "ci-smoke-" + uuid.uuid4().hex[:10]
password = secrets.token_urlsafe(30)
user = get_user_model().objects.create_user(
    username=TENANT_PREFIX, password=password, is_active=True
)
tenants = []

cookies = {}


def call(method: str, path: str, payload=None, csrf=True):
    headers = {
        "Host": PUBLIC_HOST,
        "X-Forwarded-Proto": "https",
        "Accept": "application/json",
    }
    if cookies:
        headers["Cookie"] = "; ".join(name + "=" + value for name, value in cookies.items())
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://" + PUBLIC_HOST
        body = json.dumps(payload)
    if csrf:
        token = cookies.get("csrftoken")
        if token:
            headers["X-CSRFToken"] = token
    conn = http.client.HTTPConnection("frontend", 8080, timeout=15)
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        status = response.status
        response_headers = response.getheaders()
        output = response.read()
    finally:
        conn.close()

    for name, value in response_headers:
        if name.lower() == "set-cookie":
            jar = SimpleCookie()
            jar.load(value)
            for key, morsel in jar.items():
                if not morsel.value or morsel["max-age"] == "0":
                    cookies.pop(key, None)
                else:
                    cookies[key] = morsel.value

    try:
        parsed = json.loads(output)
    except (ValueError, UnicodeDecodeError):
        parsed = {}
    return status, parsed, response_headers


def has_secure_cookie(headers, name, http_only=False):
    for header, value in headers:
        if header.lower() != "set-cookie":
            continue
        jar = SimpleCookie()
        jar.load(value)
        if name in jar:
            morsel = jar[name]
            return bool(morsel["secure"]) and (not http_only or bool(morsel["httponly"]))
    return False


try:
    owned = Tenant.objects.create(name="CI Smoke Owned", slug=TENANT_PREFIX+"-a")
    other = Tenant.objects.create(name="CI Smoke Foreign", slug=TENANT_PREFIX+"-b")
    tenants.extend([owned, other])
    TenantMembership.objects.create(user=user, tenant=owned, role=TenantMembership.Role.OWNER)

    status, session, headers = call("GET", "/api/v1/auth/session/")
    assert status == 200 and session["authenticated"] is False, (status, session)
    assert session["tenants"] == []
    assert has_secure_cookie(headers, "csrftoken"), "CSRF Secure cookie missing"
    assert "csrftoken" in cookies

    status, _, _ = call(
        "POST", "/api/v1/auth/login/",
        {"username": user.username, "password": password}, csrf=False
    )
    assert status == 403, "Anonymous POST without CSRF should be rejected"

    status, logged, headers = call(
        "POST", "/api/v1/auth/login/",
        {"username": user.username, "password": password}
    )
    assert status == 200 and logged["authenticated"] is True, status
    assert has_secure_cookie(headers, "sessionid", http_only=True), "Session cookie must be Secure/HttpOnly"

    status, logged_session, _ = call("GET", "/api/v1/auth/session/")
    assert status == 200 and logged_session["authenticated"] is True
    assert len(logged_session["tenants"]) == 1
    assert logged_session["tenants"][0]["id"] == str(owned.pk)
    assert str(other.pk) not in json.dumps(logged_session)

    margin = {
        "eligible_subtotal_cents": 20000,
        "existing_discounts_cents": 1000,
        "cost_of_goods_cents": 10000,
        "payment_fee_cents": 500,
        "shipping_subsidy_cents": 1000,
        "other_variable_costs_cents": 500,
        "proposed_cashback_bps": 200,
        "minimum_margin_bps": 1500,
    }

    own_margin = f"/api/v1/tenants/{owned.pk}/margin-simulations/"
    other_margin = f"/api/v1/tenants/{other.pk}/margin-simulations/"
    own_plan = f"/api/v1/tenants/{owned.pk}/campaign-plans/preview/"
    other_plan = f"/api/v1/tenants/{other.pk}/campaign-plans/preview/"

    status, result, _ = call("POST", own_margin, margin)
    assert status == 200 and result["status"] == "within_target", (status, result)
    assert result["estimated_cashback_exposure_cents"] == 380
    assert result["automatically_approved"] is False

    status, _, _ = call("POST", other_margin, margin)
    assert status == 404, "Cross-tenant simulation must be blocked"

    plan = {**margin, "projected_paid_orders": 100,
            "campaign_budget_cents": 10000, "already_committed_cents": 2000}
    status, result, _ = call("POST", own_plan, plan)
    assert status == 200 and result["status"] == "campaign_budget_exceeded", (status, result)
    assert result["projected_new_exposure_cents"] == 38000
    assert result["automatically_approved"] is False

    status, _, _ = call("POST", other_plan, plan)
    assert status == 404, "Cross-tenant campaign planning must be blocked"

    status, _, _ = call("POST", "/api/v1/auth/logout/", {}, csrf=False)
    assert status == 403, "Logout without CSRF should be rejected"

    status, result, _ = call("POST", "/api/v1/auth/logout/", {})
    assert status == 200 and result["authenticated"] is False

    status, anon, _ = call("GET", "/api/v1/auth/session/")
    assert status == 200 and anon["authenticated"] is False
    assert anon["tenants"] == []
    status, _, _ = call("POST", own_margin, margin)
    assert status in (401, 403), "Logged-out user must not simulate"

    print("CI_REAL_AUTH_INTEGRATION_OK: login, CSRF, session, tenants, margin, campaign, logout")
finally:
    for item in tenants:
        item.delete()
    user.delete()
