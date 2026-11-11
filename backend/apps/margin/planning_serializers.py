from rest_framework import serializers

from .serializers import MONEY_LIMIT, MarginSimulationSerializer


class CampaignPlanningSerializer(MarginSimulationSerializer):
    """Estende a simulação por pedido com hipótese de volume e limite mensal."""

    projected_paid_orders = serializers.IntegerField(min_value=1, max_value=50000)
    campaign_budget_cents = serializers.IntegerField(min_value=0, max_value=MONEY_LIMIT)
    already_committed_cents = serializers.IntegerField(
        min_value=0, max_value=MONEY_LIMIT, default=0
    )
