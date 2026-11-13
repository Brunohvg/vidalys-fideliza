"""Fila operacional LGPD: visível somente a administradores internos do Django.

Não permitir marcar exclusões como concluídas por engano via formulário.
"""
from django.contrib import admin
from .privacy_models import PrivacyWebhookRequest
from .models import NuvemshopInstallation


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


@admin.register(NuvemshopInstallation)
class NuvemshopInstallationAdmin(admin.ModelAdmin):
    """Auditoria da instalação: nenhum segredo/token é exibido ou editável."""
    list_display = (
        "tenant", "store_id", "client_id", "link_integrity",
        "connected_at", "updated_at",
    )
    list_filter = ("connected_at",)
    search_fields = ("tenant__name", "tenant__slug", "store_id", "client_id")
    list_select_related = ("tenant", "connected_by")
    readonly_fields = (
        "tenant", "store_id", "client_id", "scope", "connected_by",
        "connected_at", "updated_at", "link_integrity",
    )
    fields = readonly_fields
    ordering = ("-updated_at",)
    list_per_page = 30
    actions = None

    @admin.display(description="Vínculo com empresa")
    def link_integrity(self, obj):
        if (obj.tenant.platform == "nuvemshop"
                and obj.tenant.external_store_id == obj.store_id):
            return "Consistente (token não verificado)"
        return "DIVERGENTE — revisar sem alterar automaticamente"

    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
