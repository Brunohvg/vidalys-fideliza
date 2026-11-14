"""Primeira página de pedidos Nuvemshop, sem PII e sem eventos financeiros locais."""
from django.conf import settings
from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation
from .order_preview_views import OrderPreviewView
from .order_readonly import OrderReadError, safe_id, read_orders_page, summarize_order
from .scopes import has_order_access, has_customer_access
from .security import OAuthConfigurationError, config, decrypt_token
from .views import member_for


class RecentOrdersPreviewView(APIView):
    """GET do provedor autorizado: não importa nem persiste clientes ou pedidos."""
    permission_classes=[IsAuthenticated]
    http_method_names=["get","head","options"]

    def get(self,request,tenant_id):
        answer=OrderPreviewView.answer
        member=member_for(request.user,tenant_id)
        tenant=member.tenant
        if member.role not in (TenantMembership.Role.OWNER,TenantMembership.Role.ADMIN):
            return answer({"detail":"Acesso restrito à administração."},403)
        if tenant.status!=Tenant.Status.ACTIVE or tenant.platform!="nuvemshop":
            return answer({"detail":"Loja Nuvemshop indisponível."},409)
        if not settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED:
            return answer({"detail":"Consulta de pedidos desativada."},409)
        try:
            cfg=config()
        except OAuthConfigurationError:
            return answer({"detail":"Integração indisponível."},503)
        installed=NuvemshopInstallation.objects.filter(tenant=tenant).first()
        if (not installed or installed.client_id!=cfg.client_id
                or installed.store_id!=str(tenant.external_store_id)
                or not has_order_access(installed.scope,preview_enabled=True)):
            return answer({"detail":"Autorize a leitura de pedidos nesta loja."},409)
        if not cache.add(f"fideliza:recent-orders:{tenant.pk}",1,timeout=20):
            return answer({"detail":"Consulta recente. Aguarde para atualizar."},429)
        try:
            token=decrypt_token(installed.token_ciphertext,cfg.token_keys)
            source=read_orders_page(store_id=int(installed.store_id),
                                    access_token=token,user_agent=cfg.user_agent)
            ids=set()
            if (settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
                    and has_customer_access(installed.scope,customer_preview_enabled=True)):
                ids={
                    safe_id(item["customer"]["id"])
                    for item in source
                    if isinstance(item.get("customer"),dict)
                       and safe_id(item["customer"].get("id"))
                }
            linked=set(ProgramParticipant.objects.filter(
                tenant=tenant,status=ProgramParticipant.Status.ACTIVE,
                external_customer_id__in=ids,
            ).values_list("external_customer_id",flat=True)) if ids else set()
            items=[]
            for item in source:
                order_id=safe_id(item.get("id"))
                if not order_id:
                    raise OrderReadError("Pedido sem ID válido")
                customer=item.get("customer")
                cid=safe_id(customer.get("id")) if isinstance(customer,dict) else None
                items.append(summarize_order(
                    item,order_id=order_id,
                    participant_verified=bool(cid and cid in linked),
                ))
            return answer({
                "mode":"read_only","source":"nuvemshop_live_read_only",
                "items":items,"page":1,"page_size":10,
                "points_credited":False,"coupons_created":False,
                "read_only":True,
                "note":"Consulta da primeira página da loja; pagamento não comprova captura financeira.",
            })
        except OAuthConfigurationError:
            return answer({"detail":"Credencial da loja indisponível."},503)
        except (ValueError,OrderReadError):
            return answer({"detail":"Não foi possível consultar os pedidos desta loja."},502)
