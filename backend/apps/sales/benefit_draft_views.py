"""Rascunhos de benefícios. Sem publicar cupom, debitar pontos ou enviar campanha."""
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant
from .models import DiscountRewardDraft, PointCampaignDraft
from .views import staff_member, safe_reply


def _allowed(request, tenant_id, writing=False):
    membership = staff_member(request.user, tenant_id)
    if membership is None:
        return None, safe_reply({"detail":"Somente administradores podem gerenciar benefícios."}, 403)
    if writing and membership.tenant.status != Tenant.Status.ACTIVE:
        return None, safe_reply({"detail":"Esta loja não está ativa."}, 409)
    return membership, None


def _int(value, start, end):
    return type(value) is int and start <= value <= end


def _reward(item):
    return {
        "id":str(item.id),"title":item.title,"points_cost":item.points_cost,
        "discount_cents":item.discount_cents,
        "min_order_cents":item.min_order_cents,
        "max_redemptions":item.max_redemptions,
        "status":"draft","published":False,"redemption_enabled":False,
    }


class DiscountRewardDraftsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get","post","head","options"]

    def get(self, request, tenant_id):
        member,err = _allowed(request,tenant_id)
        if err is not None:return err
        items = DiscountRewardDraft.objects.filter(tenant_id=tenant_id)[:30]
        return safe_reply({"mode":"draft_only","activation_available":False,
                           "items":[_reward(i) for i in items]})

    @transaction.atomic
    def post(self, request, tenant_id):
        member,err = _allowed(request,tenant_id,writing=True)
        if err is not None:return err
        data=request.data
        keys={"title","points_cost","discount_cents","min_order_cents","max_redemptions"}
        if not isinstance(data,dict) or set(data)!=keys:
            return safe_reply({"detail":"Preencha os cinco campos da recompensa."},400)
        title=data["title"]
        if not (isinstance(title,str) and 4 <= len(title.strip()) <= 100
                and _int(data["points_cost"],1,1_000_000)
                and _int(data["discount_cents"],100,1_000_000)
                and _int(data["min_order_cents"],0,100_000_000)
                and _int(data["max_redemptions"],1,100_000)
                and data["min_order_cents"] >= data["discount_cents"]):
            return safe_reply({"detail":"Revise os limites: desconto mínimo R$ 1,00 e pedido mínimo maior ou igual ao desconto."},400)
        Tenant.objects.select_for_update().get(pk=tenant_id)
        if DiscountRewardDraft.objects.filter(tenant_id=tenant_id).count() >= 30:
            return safe_reply({"detail":"Limite de 30 rascunhos por loja."},409)
        obj=DiscountRewardDraft.objects.create(
            tenant_id=tenant_id,title=title.strip(),
            points_cost=data["points_cost"],discount_cents=data["discount_cents"],
            min_order_cents=data["min_order_cents"],
            max_redemptions=data["max_redemptions"],updated_by=request.user,
        )
        return safe_reply({"mode":"draft_only","reward":_reward(obj),
                           "points_credited":False,"coupon_created":False},201)


def _campaign(obj):
    return {
        "id":str(obj.id),"goal":obj.goal,
        "bonus_points":obj.bonus_points,"max_customers":obj.max_customers,
        "maximum_bonus_points":obj.bonus_points * obj.max_customers,
        "status":"draft","published":False,"sending_enabled":False,
    }


class PointCampaignDraftsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get","post","head","options"]

    def get(self,request,tenant_id):
        member,err=_allowed(request,tenant_id)
        if err is not None:return err
        items=PointCampaignDraft.objects.filter(tenant_id=tenant_id)[:30]
        return safe_reply({"mode":"draft_only","activation_available":False,
                           "items":[_campaign(i) for i in items]})

    @transaction.atomic
    def post(self,request,tenant_id):
        member,err=_allowed(request,tenant_id,writing=True)
        if err is not None:return err
        data=request.data
        if not isinstance(data,dict) or set(data)!={"goal","bonus_points","max_customers"}:
            return safe_reply({"detail":"Informe objetivo, pontos e limite de participantes."},400)
        if (data["goal"] not in PointCampaignDraft.Goal.values
                or not _int(data["bonus_points"],1,100_000)
                or not _int(data["max_customers"],1,50_000)
                or data["bonus_points"] * data["max_customers"] > 100_000_000):
            return safe_reply({"detail":"Objetivo ou limite de pontos inválido."},400)
        Tenant.objects.select_for_update().get(pk=tenant_id)
        if PointCampaignDraft.objects.filter(tenant_id=tenant_id).count() >= 30:
            return safe_reply({"detail":"Limite de 30 rascunhos por loja."},409)
        obj=PointCampaignDraft.objects.create(
            tenant_id=tenant_id,goal=data["goal"],bonus_points=data["bonus_points"],
            max_customers=data["max_customers"],updated_by=request.user,
        )
        return safe_reply({"mode":"draft_only","campaign":_campaign(obj),
                           "points_credited":False,"messages_sent":False},201)
