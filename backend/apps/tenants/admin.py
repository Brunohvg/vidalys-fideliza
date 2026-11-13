from django.contrib import admin
from django.db.models import Count, Q

from .models import Tenant, TenantMembership


class MembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner_count", "integration_state", "status", "external_store_id")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _owner_count=Count(
                "memberships",
                filter=Q(memberships__role=TenantMembership.Role.OWNER),
            )
        )

    @admin.display(description="Proprietários", ordering="_owner_count")
    def owner_count(self, obj):
        return obj._owner_count
    
    @admin.display(description="Integração")
    def integration_state(self, obj):
        if obj.platform == "independent":
            return "Sem integração"
        if obj.platform == "nuvemshop":
            return ("Nuvemshop (autorização registrada)"
                    if obj.external_store_id else "Nuvemshop (sem autorização)")
        return obj.platform
    search_fields = ("name", "slug", "external_store_id")
    list_filter = ("status", "platform")
    inlines = [MembershipInline]

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    """Auditoria read-only: associações são alteradas somente dentro da loja."""
    list_display = ("tenant", "member_username", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("tenant__name", "user__email", "user__username")
    list_select_related = ("tenant", "user")
    ordering = ("-created_at",)

    @admin.display(description="Usuário")
    def member_username(self, obj):
        return obj.user.get_username()

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
