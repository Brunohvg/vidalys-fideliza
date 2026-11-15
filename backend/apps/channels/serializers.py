"""Contrato HTTP compartilhado entre Flow, PDV e adaptadores internos."""
import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.customers.services import normalize_email, normalize_phone
from apps.sales.models import SaleRecord


SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
MONEY = re.compile(r"^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,2})?$")


class MoneyCentsField(serializers.Field):
    """Dinheiro entra como string decimal; nunca converter ponto flutuante."""

    def to_internal_value(self, value):
        if not isinstance(value, str) or not MONEY.fullmatch(value):
            raise serializers.ValidationError("Use valor decimal em string, ex. 149.90.")
        cents = int(Decimal(value) * 100)
        if cents > 100_000_000:
            raise serializers.ValidationError("Valor excede o limite por pedido.")
        return cents

    def to_representation(self, value):
        return f"{value // 100}.{value % 100:02d}"


class OrderEventSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    channel = serializers.ChoiceField(choices=[
        SaleRecord.Channel.VIDALYS_FLOW, SaleRecord.Channel.COUNTER,
        SaleRecord.Channel.NUVEMSHOP,
    ])
    external_order_id = serializers.RegexField(SAFE_REFERENCE, max_length=80)
    customer_identifier = serializers.CharField(max_length=254, trim_whitespace=True)
    total_amount = MoneyCentsField()
    currency = serializers.ChoiceField(choices=["BRL"])
    status = serializers.ChoiceField(choices=SaleRecord.OrderStatus.choices)
    source_event_id = serializers.RegexField(
        SAFE_REFERENCE, max_length=80, required=False,
    )
    occurred_at = serializers.DateTimeField(required=False, allow_null=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Informe um objeto JSON.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError("Campos adicionais não são aceitos.")
        return super().to_internal_value(data)

    def validate_customer_identifier(self, value):
        try:
            return normalize_email(value) if "@" in value else normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        if attrs["status"] in (SaleRecord.OrderStatus.PENDING, SaleRecord.OrderStatus.PAID):
            if attrs["total_amount"] == 0:
                raise serializers.ValidationError({"total_amount": "Venda pendente ou paga precisa de valor."})
        when = attrs.get("occurred_at")
        if when is not None:
            if not timezone.is_aware(when):
                raise serializers.ValidationError({"occurred_at": "Informe fuso horário."})
            now = timezone.now()
            if when > now + timedelta(minutes=5) or when < now - timedelta(days=365 * 5):
                raise serializers.ValidationError({"occurred_at": "Data fora do intervalo permitido."})
        return attrs
