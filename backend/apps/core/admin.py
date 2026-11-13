"""Auditoria de cadastros de lojistas, somente para superusuários.

Nunca editar registros pendentes pelo Django Admin: a confirmação HMAC
é a única operação que pode criar uma conta e seu tenant.
"""
from django.contrib import admin
from django.utils import timezone
from .models import MerchantRegistration


@admin.register(MerchantRegistration)
class MerchantRegistrationAdmin(admin.ModelAdmin):
    list_display = ("store_name", "masked_email", "registration_state",
                    "requested_at", "expires_at")
    list_filter = ("consumed_at",)
    search_fields = ("store_name", "normalized_email")
    ordering = ("-requested_at",)
    readonly_fields = ("store_name", "masked_email", "first_name",
                       "requested_at", "expires_at", "consumed_at",
                       "registration_state")
    fields = ("store_name", "masked_email", "first_name",
              "registration_state", "requested_at", "expires_at", "consumed_at")
    list_per_page = 50

    @admin.display(description="E-mail")
    def masked_email(self, obj):
        try:
            local, domain = obj.normalized_email.rsplit("@", 1)
            return local[:2] + "•••@" + domain
        except ValueError:
            return "—"

    @admin.display(description="Estado")
    def registration_state(self, obj):
        if obj.consumed_at:
            return "Confirmado"
        if obj.expires_at <= timezone.now():
            return "Expirado"
        return "Aguardando confirmação"

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import EmailDispatch


@admin.register(EmailDispatch)
class EmailDispatchAdmin(admin.ModelAdmin):
    """Histórico de estados, nunca dados pessoais nem payload."""
    list_display = ("created_at", "kind", "state", "queue_seconds", "smtp_seconds",
                    "published_at", "started_at", "finished_at", "attempts", "failure_type")
    list_filter = ("kind", "state")
    readonly_fields = ("id", "kind", "reference_id", "state", "created_at",
                       "published_at", "started_at", "finished_at",
                       "attempts", "failure_type")
    fields = readonly_fields
    ordering = ("-created_at",)
    list_per_page = 50

    @admin.display(description="Espera fila (s)")
    def queue_seconds(self, obj):
        if obj.published_at and obj.started_at:
            return max(0, round((obj.started_at - obj.published_at).total_seconds(), 1))
        return "—"

    @admin.display(description="Tempo SMTP (s)")
    def smtp_seconds(self, obj):
        if obj.started_at and obj.finished_at:
            return max(0, round((obj.finished_at - obj.started_at).total_seconds(), 1))
        return "—"

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
