from rest_framework import serializers

from .models import CostItem

MAX_CENTS = 1_000_000_000


class CostItemSerializer(serializers.ModelSerializer):
    review_status = serializers.CharField(read_only=True)
    verified_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CostItem
        fields = [
            "id", "reference", "sku", "external_variant_id", "name",
            "unit_cost_cents", "selling_price_cents", "provenance",
            "verified_at", "verified_by_name", "version", "review_status",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_verified_by_name(self, obj):
        return obj.verified_by.get_username() if obj.verified_by else None


class CostWriteSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100, trim_whitespace=True, required=False)
    sku = serializers.CharField(max_length=100, trim_whitespace=True, allow_blank=True, required=False)
    external_variant_id = serializers.CharField(max_length=64, trim_whitespace=True, allow_blank=True, required=False)
    name = serializers.CharField(max_length=180, trim_whitespace=True, required=False)
    unit_cost_cents = serializers.IntegerField(min_value=1, max_value=MAX_CENTS, allow_null=True, required=False)
    selling_price_cents = serializers.IntegerField(min_value=1, max_value=MAX_CENTS, allow_null=True, required=False)
    verify_cost = serializers.BooleanField(default=False)
    provenance = serializers.CharField(max_length=240, trim_whitespace=True, allow_blank=True, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if "reference" in attrs:
            attrs["reference"] = attrs["reference"].strip().upper()
        if "sku" in attrs:
            attrs["sku"] = attrs["sku"].strip().upper()
        if "external_variant_id" in attrs:
            attrs["external_variant_id"] = attrs["external_variant_id"].strip()
        if "reference" in attrs and not attrs["reference"]:
            raise serializers.ValidationError({"reference": "Identificador não pode ser vazio."})
        if attrs.get("verify_cost"):
            if len(attrs.get("provenance", "").strip()) < 8:
                raise serializers.ValidationError({"provenance": "Informe a origem da conferência (mínimo 8 caracteres)."})
        return attrs
