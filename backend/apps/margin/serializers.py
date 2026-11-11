from rest_framework import serializers


MONEY_LIMIT = 1_000_000_000  # R$ 10 milhões por simulação: evita abuso e overflow em clientes.


class MarginSimulationSerializer(serializers.Serializer):
    # Todos os valores monetários em centavos inteiros, nunca float.
    eligible_subtotal_cents = serializers.IntegerField(min_value=1, max_value=MONEY_LIMIT)
    existing_discounts_cents = serializers.IntegerField(
        min_value=0, max_value=MONEY_LIMIT, default=0
    )
    cost_of_goods_cents = serializers.IntegerField(
        min_value=0, max_value=MONEY_LIMIT, allow_null=True,
        default=None, required=False
    )
    payment_fee_cents = serializers.IntegerField(min_value=0, max_value=MONEY_LIMIT, default=0)
    shipping_subsidy_cents = serializers.IntegerField(min_value=0, max_value=MONEY_LIMIT, default=0)
    other_variable_costs_cents = serializers.IntegerField(
        min_value=0, max_value=MONEY_LIMIT, default=0
    )
    proposed_cashback_bps = serializers.IntegerField(min_value=0, max_value=10000, default=200)
    minimum_margin_bps = serializers.IntegerField(min_value=0, max_value=10000, default=1000)

    def validate(self, attrs):
        subtotal = attrs["eligible_subtotal_cents"]
        discounts = attrs["existing_discounts_cents"]
        if discounts >= subtotal:
            raise serializers.ValidationError({
                "existing_discounts_cents": "Descontos precisam ser menores que o subtotal elegível."
            })
        return attrs
