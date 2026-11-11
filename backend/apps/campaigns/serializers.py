"""Contrato estrito de rascunho: não aceita status, aprovação ou publicação."""
from rest_framework import serializers

from .models import CampaignDraft


GOAL_LABELS = {
    "second_purchase": "Segunda compra",
    "reactivation": "Reativação",
    "recurrence": "Recorrência",
}


def preview(draft):
    benefit = (draft.ticket_cents * draft.cashback_rate_bps + 5000) // 10000
    exposure = benefit * draft.projected_paid_orders
    return {
        "credit_per_order_cents": benefit,
        "max_exposure_cents": exposure,
        "exceeds_budget": exposure > draft.budget_cents,
        "assumptions_only": True,
    }


class CampaignDraftSerializer(serializers.ModelSerializer):
    preview = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = CampaignDraft
        fields = [
            "id", "title", "goal", "cashback_rate_bps",
            "ticket_cents", "projected_paid_orders", "budget_cents",
            "version", "created_at", "updated_at", "status", "preview",
        ]
        read_only_fields = [
            "id", "version", "created_at", "updated_at", "status", "preview",
        ]
        extra_kwargs = {
            "title": {"allow_blank": False, "max_length": 90},
            "goal": {"required": True},
            "cashback_rate_bps": {"min_value": 1, "max_value": 1000},
            "ticket_cents": {"min_value": 1, "max_value": 1_000_000_000},
            "budget_cents": {"min_value": 1, "max_value": 1_000_000_000},
            "projected_paid_orders": {"min_value": 1, "max_value": 50_000},
        }

    def validate_title(self, title):
        title = title.strip()
        if not title or any(ord(char) < 32 for char in title):
            raise serializers.ValidationError("Informe um nome legível para o rascunho.")
        return title

    def get_status(self, obj):
        return "draft"

    def get_preview(self, obj):
        return preview(obj)


WRITABLE_FIELDS = frozenset([
    "title", "goal", "cashback_rate_bps", "ticket_cents",
    "projected_paid_orders", "budget_cents",
])
