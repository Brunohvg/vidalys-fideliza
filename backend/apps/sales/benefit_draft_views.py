"""Rascunhos de benefícios. Sem publicar cupom, debitar pontos ou enviar campanha."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
        "status":item.publication_status,
        "published":item.publication_status == DiscountRewardDraft.PublicationStatus.PUBLISHED,
        "published_at":item.published_at.isoformat() if item.published_at else None,
        "redemption_enabled":False,
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



class DiscountRewardDraftDetailView(APIView):
    """Editar e excluir apenas rascunhos. Nunca cria descontos ou publica benefícios."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch", "delete", "options"]

    @transaction.atomic
    def patch(self, request, tenant_id, reward_id):
        member, err = _allowed(request, tenant_id, writing=True)
        if err is not None:
            return err
        obj = get_object_or_404(
            DiscountRewardDraft.objects.select_for_update(),
            pk=reward_id, tenant_id=tenant_id,
        )
        if obj.publication_status == DiscountRewardDraft.PublicationStatus.PUBLISHED:
            return safe_reply({"detail":"Despublique a recompensa antes de editar."},409)
        keys = {"title", "points_cost", "discount_cents", "min_order_cents", "max_redemptions"}
        data = request.data
        if not isinstance(data, dict) or set(data) != keys:
            return safe_reply({"detail": "Preencha os cinco campos da recompensa."}, 400)
        title = data["title"]
        if not (isinstance(title, str) and 4 <= len(title.strip()) <= 100
                and _int(data["points_cost"], 1, 1_000_000)
                and _int(data["discount_cents"], 100, 1_000_000)
                and _int(data["min_order_cents"], 0, 100_000_000)
                and _int(data["max_redemptions"], 1, 100_000)
                and data["min_order_cents"] >= data["discount_cents"]):
            return safe_reply({"detail": "Confira pontos, desconto, pedido mínimo e limites."}, 400)
        obj.title = title.strip()
        obj.points_cost = data["points_cost"]
        obj.discount_cents = data["discount_cents"]
        obj.min_order_cents = data["min_order_cents"]
        obj.max_redemptions = data["max_redemptions"]
        obj.updated_by = request.user
        obj.save(update_fields=[
            "title", "points_cost", "discount_cents", "min_order_cents",
            "max_redemptions", "updated_by",
        ])
        return safe_reply({"mode": "draft_only", "reward": _reward(obj), "coupon_created": False})

    @transaction.atomic
    def delete(self, request, tenant_id, reward_id):
        member, err = _allowed(request, tenant_id, writing=True)
        if err is not None:
            return err
        obj = get_object_or_404(
            DiscountRewardDraft.objects.select_for_update(),
            pk=reward_id, tenant_id=tenant_id,
        )
        if obj.publication_status == DiscountRewardDraft.PublicationStatus.PUBLISHED:
            return safe_reply({"detail":"Despublique a recompensa antes de excluir."},409)
        obj.delete()
        return safe_reply({"deleted": True, "id": str(reward_id), "coupon_created": False})

class DiscountRewardPublicationView(APIView):
    """Publica/despublica somente o CATÁLOGO. Não emite cupom nem debita pontos."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch", "options"]

    @transaction.atomic
    def patch(self, request, tenant_id, reward_id):
        member, err = _allowed(request, tenant_id, writing=True)
        if err is not None:
            return err
        data = request.data
        if not isinstance(data, dict) or set(data) != {"published"} or type(data["published"]) is not bool:
            return safe_reply({"detail":"Informe somente published=true ou false."},400)
        obj = get_object_or_404(
            DiscountRewardDraft.objects.select_for_update(), pk=reward_id, tenant_id=tenant_id,
        )
        published = data["published"]
        wanted = (
            DiscountRewardDraft.PublicationStatus.PUBLISHED if published
            else DiscountRewardDraft.PublicationStatus.DRAFT
        )
        if obj.publication_status != wanted:
            obj.publication_status = wanted
            obj.published_at = timezone.now() if published else None
            obj.updated_by = request.user
            obj.save(update_fields=["publication_status","published_at","updated_by"])
        return safe_reply({
            "reward":_reward(obj), "catalog_published":published,
            "redemption_enabled":False,"coupon_created":False,
            "points_credited":False,"points_debited":False,
        })


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


class PointCampaignDraftDetailView(APIView):
    """Manutenção local de planejamento. Nunca publica nem envia mensagens."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch", "delete", "options"]

    @transaction.atomic
    def patch(self, request, tenant_id, campaign_id):
        member, err = _allowed(request, tenant_id, writing=True)
        if err is not None:
            return err
        obj = get_object_or_404(
            PointCampaignDraft.objects.select_for_update(),
            pk=campaign_id, tenant_id=tenant_id,
        )
        data = request.data
        if not isinstance(data, dict) or set(data) != {"goal", "bonus_points", "max_customers"}:
            return safe_reply({"detail": "Informe objetivo, pontos e limite de participantes."}, 400)
        if (data["goal"] not in PointCampaignDraft.Goal.values
                or not _int(data["bonus_points"], 1, 100_000)
                or not _int(data["max_customers"], 1, 50_000)
                or data["bonus_points"] * data["max_customers"] > 100_000_000):
            return safe_reply({"detail": "Objetivo ou limites de pontos inválidos."}, 400)
        obj.goal = data["goal"]
        obj.bonus_points = data["bonus_points"]
        obj.max_customers = data["max_customers"]
        obj.updated_by = request.user
        obj.save(update_fields=["goal", "bonus_points", "max_customers", "updated_by"])
        return safe_reply({"mode": "draft_only", "campaign": _campaign(obj), "messages_sent": False})

    @transaction.atomic
    def delete(self, request, tenant_id, campaign_id):
        member, err = _allowed(request, tenant_id, writing=True)
        if err is not None:
            return err
        obj = get_object_or_404(
            PointCampaignDraft.objects.select_for_update(),
            pk=campaign_id, tenant_id=tenant_id,
        )
        obj.delete()
        return safe_reply({"deleted": True, "id": str(campaign_id), "messages_sent": False})
