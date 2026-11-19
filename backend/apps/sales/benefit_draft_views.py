"""Rascunhos de benefícios e campanhas. Sem creditar pontos, debitar ou enviar mensagens."""
from datetime import date

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant
from .campaign_engine import audience, default_text, params_of, phase, result
from .models import DiscountRewardDraft, PointCampaignDraft
from .views import staff_member, safe_reply


def _allowed(request, tenant_id, writing=False):
    membership = staff_member(request.user, tenant_id)
    if membership is None:
        return None, safe_reply({"detail":"Somente administradores podem gerenciar benefícios."}, 403)
    if writing and membership.tenant.status != Tenant.Status.ACTIVE:
        return None, safe_reply({"detail":"Esta loja não está ativa."}, 409)
    return membership, None


def _channels_for(tenant):
    """Recompensa criada no painel vale em todos os canais da loja.

    O padrão do modelo (balcão + Flow) deixava toda recompensa trancada no Meu
    Clube das lojas Nuvemshop, que só libera troca com "nuvemshop" no canal.
    Isto não ativa resgate: a troca online continua dependendo das flags e da
    homologação do checkout.
    """
    channels = ["counter", "vidalys_flow"]
    if tenant.platform == "nuvemshop":
        channels.insert(0, "nuvemshop")
    return ",".join(channels)


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
            allowed_channels=_channels_for(member.tenant),
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


REQUIRED = {"goal", "bonus_points", "max_customers"}
OPTIONAL = {"title", "message", "starts_on", "ends_on", "window_days", "inactive_days",
            "near_points", "multiplier", "holdout_percent"}
DEFAULTS = {"title": "", "message": "", "starts_on": None, "ends_on": None, "window_days": 30,
            "inactive_days": 60, "near_points": 100, "multiplier": 2, "holdout_percent": 10}


def _date(value):
    if value is None:
        return None, True
    if not isinstance(value, str):
        return None, False
    try:
        return date.fromisoformat(value), True
    except ValueError:
        return None, False


def _campaign_input(data, base=None):
    """Valida e devolve (params, erro). base preenche o que não veio (edição)."""
    if not isinstance(data, dict) or not REQUIRED <= set(data) <= REQUIRED | OPTIONAL:
        return None, "Informe objetivo, pontos e limite de participantes."
    params = dict(DEFAULTS if base is None else base)
    params.update(data)
    if (params["goal"] not in PointCampaignDraft.Goal.values
            or not _int(params["bonus_points"], 1, 100_000)
            or not _int(params["max_customers"], 1, 50_000)
            or params["bonus_points"] * params["max_customers"] > 100_000_000):
        return None, "Objetivo ou limite de pontos inválido."
    if (not _int(params["window_days"], 1, 365) or not _int(params["inactive_days"], 15, 730)
            or not _int(params["near_points"], 1, 100_000) or not _int(params["multiplier"], 2, 5)
            or not _int(params["holdout_percent"], 0, 50)):
        return None, "Ajuste os parâmetros do público."
    for key, size in (("title", 80), ("message", 180)):
        if not isinstance(params[key], str) or len(params[key].strip()) > size:
            return None, "Título ou mensagem muito longos."
        params[key] = params[key].strip()
    for key in ("starts_on", "ends_on"):
        value = params[key]
        if isinstance(value, date):
            continue
        parsed, ok = _date(value)
        if not ok:
            return None, "Data inválida."
        params[key] = parsed
    if params["starts_on"] and params["ends_on"]:
        if params["ends_on"] < params["starts_on"]:
            return None, "O fim precisa ser depois do início."
        if (params["ends_on"] - params["starts_on"]).days > 92:
            return None, "Campanhas duram no máximo 3 meses."
    return params, None


def _campaign(obj, *, with_result=False):
    params = params_of(obj)
    title, message = default_text(obj)
    data = {
        "id":str(obj.id),"goal":obj.goal,
        "bonus_points":obj.bonus_points,"max_customers":obj.max_customers,
        "maximum_bonus_points":obj.bonus_points * obj.max_customers,
        "title":obj.title,"message":obj.message,
        "display_title":obj.title or title,"display_message":obj.message or message,
        "starts_on":obj.starts_on.isoformat() if obj.starts_on else None,
        "ends_on":obj.ends_on.isoformat() if obj.ends_on else None,
        "window_days":obj.window_days,"inactive_days":obj.inactive_days,
        "near_points":obj.near_points,"multiplier":obj.multiplier,
        "holdout_percent":obj.holdout_percent,
        "status":phase(obj),"published":obj.published_at is not None,
        "published_at":obj.published_at.isoformat() if obj.published_at else None,
        "sending_enabled":False,"points_credited":False,
        "audience":audience(obj.id, obj.tenant_id, params),
    }
    if with_result:
        data["result"] = result(obj)
    return data


def _save(obj, params, user):
    for key, value in params.items():
        setattr(obj, key, value)
    obj.updated_by = user
    obj.save()
    return obj


class PointCampaignDraftsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get","post","head","options"]

    def get(self,request,tenant_id):
        member,err=_allowed(request,tenant_id)
        if err is not None:return err
        items=PointCampaignDraft.objects.filter(tenant_id=tenant_id)[:30]
        return safe_reply({"mode":"offer_only","activation_available":False,
                           "items":[_campaign(i, with_result=True) for i in items]})

    @transaction.atomic
    def post(self,request,tenant_id):
        member,err=_allowed(request,tenant_id,writing=True)
        if err is not None:return err
        params,error=_campaign_input(request.data)
        if error:
            return safe_reply({"detail":error},400)
        Tenant.objects.select_for_update().get(pk=tenant_id)
        if PointCampaignDraft.objects.filter(tenant_id=tenant_id).count() >= 30:
            return safe_reply({"detail":"Limite de 30 campanhas por loja."},409)
        obj=_save(PointCampaignDraft(tenant_id=tenant_id),params,request.user)
        return safe_reply({"mode":"draft_only","campaign":_campaign(obj),
                           "points_credited":False,"messages_sent":False},201)


class PointCampaignAudienceView(APIView):
    """Prévia ao vivo do público e do custo. Não grava nada."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id):
        member, err = _allowed(request, tenant_id)
        if err is not None:
            return err
        params, error = _campaign_input(request.data)
        if error:
            return safe_reply({"detail": error}, 400)
        preview_id = request.data.get("title", "") + str(tenant_id)
        return safe_reply({"audience": audience(preview_id, tenant_id, params), "saved": False})


class PointCampaignPublishView(APIView):
    """Publicar mostra a oferta no Meu Clube. Não credita pontos nem envia mensagens."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id, campaign_id):
        member, err = _allowed(request, tenant_id, writing=True)
        if err is not None:
            return err
        obj = get_object_or_404(PointCampaignDraft.objects.select_for_update(),
                                pk=campaign_id, tenant_id=tenant_id)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"published"} or type(data["published"]) is not bool:
            return safe_reply({"detail": "Informe se a campanha deve ficar no ar."}, 400)
        if data["published"]:
            today = timezone.localdate()
            if not obj.starts_on or not obj.ends_on:
                return safe_reply({"detail": "Defina início e fim antes de publicar."}, 400)
            if obj.ends_on < today:
                return safe_reply({"detail": "O período já terminou. Ajuste as datas."}, 400)
            obj.published_at = obj.published_at or timezone.now()
        else:
            obj.published_at = None
        obj.updated_by = request.user
        obj.save(update_fields=["published_at", "updated_by"])
        return safe_reply({"campaign": _campaign(obj, with_result=True),
                           "points_credited": False, "messages_sent": False})


class PointCampaignDraftDetailView(APIView):
    """Edição e exclusão. Nunca envia mensagens."""
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
        base = {key: getattr(obj, key) for key in REQUIRED | OPTIONAL}
        params, error = _campaign_input(request.data, base=base)
        if error:
            return safe_reply({"detail": error}, 400)
        if obj.published_at and obj.starts_on and obj.starts_on <= timezone.localdate():
            # Campanha já começou: mudar a regra estragaria a comparação de resultado.
            locked = {"goal", "window_days", "inactive_days", "near_points", "holdout_percent", "starts_on"}
            if any(params[key] != base[key] for key in locked):
                return safe_reply({"detail": "A campanha já começou. Só dá para mudar textos, pontos, limite e fim."}, 409)
        _save(obj, params, request.user)
        return safe_reply({"mode": "draft_only", "campaign": _campaign(obj, with_result=True), "messages_sent": False})

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
