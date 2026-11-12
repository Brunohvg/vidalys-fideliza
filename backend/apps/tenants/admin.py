from django.contrib import admin

from .models import Tenant, TenantMembership


class MembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "integration_state", "status", "external_store_id")
    
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
