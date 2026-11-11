"""OAuth restrito e leitura de amostra: não cria nem altera produtos ou créditos."""
import secrets
from django.conf import settings
from .scopes import has_product_access, has_customer_access
from datetime import timedelta
from urllib.parse import quote, urlsplit

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Upper
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.client import CatalogReadError, read_products_page
from apps.catalog.reconciliation import InvalidSnapshot, normalize_products, reconcile_products
from apps.costs.models import CostItem
from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation, OAuthAttempt
from .provider import OAuthExchangeError, exchange_code
from .security import (AUTHORIZE_HOST, OAuthConfigurationError, config,
                       decrypt_token, digest, encrypt_token)


def member_for(user, tenant_id):
    return get_object_or_404(
        TenantMembership.objects.select_related("tenant"),
        user=user, tenant_id=tenant_id,
    )


def _owner_admin(member):
    return member.role in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


def _safe_result(status, tenant_id=None):
    # Não transportar code/state/token para HTML, redirect ou histórico do navegador.
    response = HttpResponse(status=303)
    response["Location"] = "/?nuvemshop=" + status + (
        "&nuvemshop_tenant=" + str(tenant_id) if tenant_id else ""
    )
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = "no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


class NuvemshopStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id):
        member_for(request.user, tenant_id)
        installed = NuvemshopInstallation.objects.filter(tenant_id=tenant_id).first()
        try:
            cfg = config()
            configured = True
        except OAuthConfigurationError:
            cfg, configured = None, False
        customer_preview_enabled = settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
        # Distinguir "scope recebido" de "recurso habilitado" no backend.
        customer_granted = bool(installed and has_customer_access(
            installed.scope, customer_preview_enabled=True
        ))
        response = Response({
            "customer_matching": {
                "preview_enabled": customer_preview_enabled,
                "customer_scope_granted": customer_granted,
                "read_only_preview_available": bool(
                    configured and customer_preview_enabled and customer_granted and installed
                    and installed.client_id == cfg.client_id
                    and installed.store_id == member_for(request.user, tenant_id).tenant.external_store_id
                ),
                "requires_partner_portal_scope_and_reinstallation": not customer_granted,
                "will_activate_participants": False,
                "participant_approval_available": bool(
                    configured and customer_granted and installed
                    and settings.FIDELIZA_PARTICIPANT_APPROVAL_ENABLED
                    and settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
                    and installed.client_id == cfg.client_id
                    and installed.store_id == member_for(request.user, tenant_id).tenant.external_store_id
                ),
                "will_credit_cashback": False,
            },
            "configured": configured,
            "connected": installed is not None and cfg is not None
                         and installed.client_id == cfg.client_id
                         and installed.store_id == member_for(request.user, tenant_id).tenant.external_store_id,
            "store_id": installed.store_id if installed else None,
            "scope": installed.scope if installed else None,
            "mode": "read_products_only",
            "ready_for_write": False,
        })
        response["Cache-Control"] = "no-store"
        return response


class OAuthStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_id):
        member = member_for(request.user, tenant_id)
        if not _owner_admin(member):
            return Response({"detail": "Somente proprietário/administrador pode conectar a loja."}, status=403)
        try:
            cfg = config()
        except OAuthConfigurationError:
            return Response({"detail": "A conexão OAuth não está configurada no servidor."}, status=503)
        if not request.is_secure():
            return Response({"detail": "OAuth exige conexão HTTPS."}, status=403)
        if request.get_host() != urlsplit(cfg.callback_url).netloc:
            return Response({"detail": "Domínio da integração não confere com o callback configurado."}, status=400)
        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key
        if not session_key:
            return Response({"detail": "Sessão inválida."}, status=403)

        throttle_key = f"fideliza:oauth:start:{tenant_id}:{request.user.pk}"
        if not cache.add(throttle_key, 1, timeout=8):
            return Response({"detail": "Nova tentativa disponível em alguns segundos."}, status=429)

        nonce = secrets.token_urlsafe(32)
        now = timezone.now()
        OAuthAttempt.objects.filter(
            tenant_id=tenant_id, expires_at__lt=now - timedelta(days=1)
        ).delete()
        OAuthAttempt.objects.create(
            user=request.user, tenant=member.tenant,
            state_digest=digest(nonce), session_digest=digest(session_key),
            client_id=cfg.client_id, expires_at=now + timedelta(minutes=5),
        )
        response = Response({
            "authorize_url": f"{AUTHORIZE_HOST}/apps/{cfg.client_id}/authorize?state={quote(nonce)}",
            "expires_in_seconds": 300, "mode": "read_products_only",
        })
        response["Cache-Control"] = "no-store"
        return response


@never_cache
@require_GET
def oauth_callback(request):
    # O redirecionamento da Nuvemshop é GET; state fornece proteção CSRF própria.
    if not request.user.is_authenticated or not request.is_secure():
        return _safe_result("failed")
    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    if not (16 <= len(state) <= 200 and 6 <= len(code) <= 1024):
        return _safe_result("failed")
    try:
        cfg = config()
        if request.get_host() != urlsplit(cfg.callback_url).netloc:
            return _safe_result("failed")
        with transaction.atomic():
            attempt = OAuthAttempt.objects.select_for_update().select_related("tenant").get(
                state_digest=digest(state)
            )
            if (attempt.consumed_at is not None
                or attempt.expires_at <= timezone.now()
                or attempt.user_id != request.user.pk
                or attempt.client_id != cfg.client_id
                or not request.session.session_key
                or attempt.session_digest != digest(request.session.session_key)
                or not TenantMembership.objects.filter(
                    user=request.user, tenant_id=attempt.tenant_id,
                    role__in=[TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN],
                ).exists()):
                return _safe_result("failed")
            # Consumir uma única vez, ANTES de trocar o code na rede.
            attempt.consumed_at = timezone.now()
            attempt.save(update_fields=["consumed_at"])
    except (OAuthAttempt.DoesNotExist, OAuthConfigurationError):
        return _safe_result("failed")

    try:
        received = exchange_code(code, cfg.client_id, cfg.client_secret)
        ciphertext = encrypt_token(received["access_token"], cfg.token_keys)
        with transaction.atomic():
            tenant = Tenant.objects.select_for_update().get(pk=attempt.tenant_id)
            if tenant.platform != "nuvemshop":
                return _safe_result("failed")
            if tenant.external_store_id and tenant.external_store_id != received["store_id"]:
                return _safe_result("failed")
            if NuvemshopInstallation.objects.filter(
                client_id=cfg.client_id, store_id=received["store_id"]
            ).exclude(tenant_id=tenant.pk).exists():
                return _safe_result("failed")
            installed = NuvemshopInstallation.objects.select_for_update().filter(tenant=tenant).first()
            if installed:
                if (installed.client_id != cfg.client_id or
                        installed.store_id != received["store_id"]):
                    return _safe_result("failed")
                installed.token_ciphertext = ciphertext
                installed.scope = received["scope"]
                installed.connected_by = request.user
                installed.save(update_fields=[
                    "token_ciphertext", "scope", "connected_by", "updated_at"
                ])
            else:
                NuvemshopInstallation.objects.create(
                    tenant=tenant, client_id=cfg.client_id,
                    store_id=received["store_id"], scope=received["scope"],
                    token_ciphertext=ciphertext, connected_by=request.user,
                )
            if not tenant.external_store_id:
                tenant.external_store_id = received["store_id"]
                tenant.save(update_fields=["external_store_id", "updated_at"])
        return _safe_result("connected", attempt.tenant_id)
    except (OAuthExchangeError, OAuthConfigurationError, IntegrityError, Tenant.DoesNotExist):
        return _safe_result("failed")


class LiveCatalogPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id):
        member = member_for(request.user, tenant_id)
        try:
            cfg = config()
        except OAuthConfigurationError:
            return Response({"detail": "A integração está desconfigurada."}, status=503)
        installed = NuvemshopInstallation.objects.filter(
            tenant_id=tenant_id, client_id=cfg.client_id
        ).first()
        if (not installed or not has_product_access(installed.scope,
                customer_preview_enabled=settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED) or
                member.tenant.external_store_id != installed.store_id):
            return Response({"detail": "Conecte esta loja com a permissão read_products."}, status=409)

        raw_page = request.query_params.get("page", "1")
        if len(raw_page) > 5 or not raw_page.isascii() or not raw_page.isdecimal():
            return Response({"detail": "Página inválida."}, status=400)
        page = int(raw_page)
        if not 1 <= page <= 10000:
            return Response({"detail": "Página fora do limite."}, status=400)

        throttle_key = f"fideliza:nuvemshop:preview:{tenant_id}"
        if not cache.add(throttle_key, 1, timeout=15):
            return Response({"detail": "Consulta recente. Aguarde antes de atualizar."}, status=429)
        try:
            token = decrypt_token(installed.token_ciphertext, cfg.token_keys)
            products = read_products_page(
                store_id=int(installed.store_id), access_token=token,
                user_agent=cfg.user_agent, page=page, per_page=3,
            )
            if not products:
                return Response({
                    "mode": "read_only", "source": "nuvemshop_live_read_only",
                    "page": page, "empty": True, "items": [],
                    "summary": {"products": 0, "variants": 0},
                    "writes_performed": 0, "automatically_approved": False,
                })
            rows = normalize_products(products)
            ids = {r["variant_id"] for r in rows}
            skus = {r["sku"] for r in rows if r["sku"]}
            local = list(
                CostItem.objects.filter(tenant_id=tenant_id)
                .annotate(normalized_sku=Upper("sku"))
                .filter(Q(external_variant_id__in=ids) | Q(normalized_sku__in=skus))
                .only("id", "external_variant_id", "sku", "reference",
                      "unit_cost_cents", "selling_price_cents", "verified_at")
            )
            result = reconcile_products(products, local)
            result["source"] = "nuvemshop_live_read_only"
            result["page"] = page
            result["empty"] = False
            result["warnings"] = [
                "Leitura ao vivo de apenas três produtos da loja autorizada.",
                "Custo da API pode estar ausente; nenhum dado local foi alterado.",
                "Conciliação e vínculos exigem revisão humana antes de importar.",
            ]
            response = Response(result)
            response["Cache-Control"] = "no-store"
            return response
        except OAuthConfigurationError:
            return Response({"detail": "Chave de token indisponível."}, status=503)
        except CatalogReadError:
            return Response({"detail": "Falha na leitura da Nuvemshop; tente novamente."}, status=502)
        except InvalidSnapshot:
            return Response({"detail": "Página incompatível com a amostra limitada; revise os dados."}, status=422)
