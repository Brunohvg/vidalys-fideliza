"""Fila operacional LGPD: visível somente a administradores internos do Django.

Não permitir marcar exclusões como concluídas por engano via formulário.
"""
from django.contrib import admin
from .privacy_models import PrivacyWebhookRequest


@admin.register(PrivacyWebhookRequest)
class PrivacyWebhookRequestAdmin(admin.ModelAdmin):
    list_display = ("topic", "store_id", "state", "reason_code", "received_at")
    list_filter = ("topic", "state", "received_at")
    search_fields = ("store_id", "request_id", "event_key")
    readonly_fields = (
        "id", "tenant", "store_id", "customer_id", "request_id",
        "topic", "event_key", "state", "reason_code", "received_at", "processed_at",
        "report_accessed_at", "report_accessed_by", "delivery_confirmed_by",
        "report_digest",
    )
    ordering = ("-received_at",)
    list_per_page = 30

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)
