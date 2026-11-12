"""Simulador do mesmo rascunho de campanha, sem ativação nem carteira."""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .benefit_engine import BenefitRule, HypotheticalPurchase, simulate_benefit
from .models import CampaignDraft
from .views import membership_for, private


class HypotheticalPurchaseSerializer(serializers.Serializer):
    order_amount_cents = serializers.IntegerField(min_value=1, max_value=1_000_000_000)
    prior_paid_orders = serializers.IntegerField(min_value=0, max_value=50_000)
    days_since_last_paid_order = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=36_500,
    )
    committed_budget_cents = serializers.IntegerField(
        required=False, min_value=0, max_value=1_000_000_000,
    )

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("Campos inesperados na simulação.")
        if (attrs["prior_paid_orders"] == 0
                and attrs.get("days_since_last_paid_order") is not None):
            raise serializers.ValidationError(
                "Última compra não existe quando o histórico é zero."
            )
        return attrs


class BenefitSimulationView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id, draft_id):
        membership_for(request, tenant_id)
        draft = get_object_or_404(
            CampaignDraft, tenant_id=tenant_id, pk=draft_id,
        )
        if not isinstance(request.data, dict):
            return private(Response({"detail": "Envie um cenário JSON válido."}, status=400))
        form = HypotheticalPurchaseSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        purchase = HypotheticalPurchase(**form.validated_data)
        rule = BenefitRule(
            goal=draft.goal,
            rate_bps=draft.cashback_rate_bps,
            ticket_cents=draft.ticket_cents,
            projected_paid_orders=draft.projected_paid_orders,
            budget_cents=draft.budget_cents,
            version=draft.version,
        )
        result = simulate_benefit(rule, purchase)
        return private(Response({
            "draft_id": str(draft.pk),
            "draft_title": draft.title,
            **result,
        }))
