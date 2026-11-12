"""Prévia de pedido restrita ao administrador da loja, sem dados pessoais."""
from django.conf import settings
from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation
from .order_readonly import OrderReadError, OrderNotFound, read_order, summarize_order, safe_id
from .scopes import has_customer_access, has_order_access
from .security import OAuthConfigurationError, config, decrypt_token
from .views import member_for

class OrderPreviewView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @staticmethod
    def answer(data, status=200):
        response = Response(data, status=status)
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def get(self, request, tenant_id, order_id):
        member = member_for(request.user, tenant_id)
        tenant = member.tenant
        if member.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
            return self.answer({"detail": "Acesso restrito à administração."}, 403)
        if tenant.status != Tenant.Status.ACTIVE or tenant.platform != "nuvemshop":
            return self.answer({"detail": "Loja indisponível."}, 409)
        if not settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED:
            return self.answer({"detail": "Consulta de pedidos desativada."}, 409)
        if not safe_id(order_id):
            return self.answer({"detail": "Pedido inválido."}, 400)
        try:
            cfg = config()
        except OAuthConfigurationError:
            return self.answer({"detail": "Integração indisponível."}, 503)
        installed = NuvemshopInstallation.objects.filter(tenant=tenant).first()
        if (not installed or installed.client_id != cfg.client_id
                or installed.store_id != str(tenant.external_store_id)
                or not has_order_access(installed.scope, preview_enabled=True)):
            return self.answer({"detail": "Autorize a leitura de pedidos nesta loja."}, 409)
        if not cache.add(f"fideliza:order-preview:{tenant.pk}", 1, timeout=10):
            return self.answer({"detail": "Consulta recente. Aguarde antes de atualizar."}, 429)
        try:
            token = decrypt_token(installed.token_ciphertext, cfg.token_keys)
            order = read_order(
                store_id=int(installed.store_id), order_id=order_id,
                access_token=token, user_agent=cfg.user_agent,
            )
            # Nunca usar email/nome do pedido como prova de identidade.
            customer = order.get("customer")
            customer_id = safe_id(customer.get("id")) if isinstance(customer, dict) else None
            verified = bool(
                customer_id
                and has_customer_access(installed.scope, customer_preview_enabled=True)
                and settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
                and ProgramParticipant.objects.filter(
                    tenant=tenant, external_customer_id=customer_id,
                    status=ProgramParticipant.Status.ACTIVE,
                ).exists()
            )
            return self.answer(summarize_order(
                order, order_id=order_id, participant_verified=verified
            ))
        except OrderNotFound:
            return self.answer({"detail": "Pedido não encontrado."}, 404)
        except OAuthConfigurationError:
            return self.answer({"detail": "Credencial da loja indisponível."}, 503)
        except (OrderReadError, ValueError):
            return self.answer({"detail": "Não foi possível verificar o pedido."}, 502)
