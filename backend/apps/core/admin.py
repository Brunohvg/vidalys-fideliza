"""Auditoria de cadastros de lojistas, somente para superusuários.

Nunca editar registros pendentes pelo Django Admin: a confirmação HMAC
é a única operação que pode criar uma conta e seu tenant.
"""
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .merchant_auth import canonical_email
from .models import MerchantRegistration, MerchantEmailIdentity, MerchantEmailClaim


@admin.register(MerchantRegistration)
class MerchantRegistrationAdmin(admin.ModelAdmin):
    list_display = ("store_name", "masked_email", "registration_state",
                    "requested_at", "expires_at")
    list_filter = ("consumed_at", "cancelled_at", "blocked_at")
    actions = (
        "cancel_pending", "block_pending", "unblock_pending",
        "block_confirmed", "unblock_confirmed", "delete_pending",
    )
    search_fields = ("store_name", "normalized_email")
    ordering = ("-requested_at",)
    readonly_fields = ("store_name", "masked_email", "first_name",
                       "requested_at", "expires_at", "consumed_at",
                       "cancelled_at", "blocked_at", "registration_state")
    fields = ("store_name", "masked_email", "first_name",
              "registration_state", "requested_at", "expires_at", "consumed_at",
              "cancelled_at", "blocked_at")
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
        if obj.blocked_at:
            return "Acesso bloqueado" if obj.consumed_at else "Cadastro bloqueado"
        if obj.cancelled_at:
            return "Cancelado"
        if obj.consumed_at:
            identity = MerchantEmailIdentity.objects.filter(
                normalized_email=obj.normalized_email,
            ).first()
            if not identity:
                return "Confirmado — identidade não encontrada"
            if not identity.user.tenant_memberships.exists():
                return "Confirmado — SEM VÍNCULO"
            return "Confirmado — empresa vinculada"
        if obj.expires_at <= timezone.now():
            return "Expirado"
        return "Aguardando confirmação"

    def _report(self, request, changed, skipped, label):
        if changed:
            self.message_user(request, f"{changed} cadastro(s): {label}.", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} registro(s) ignorado(s): situação incompatível ou vínculo não comprovado.",
                messages.WARNING,
            )

    @admin.action(description="Cancelar cadastros pendentes (invalidar link)", permissions=["view"])
    def cancel_pending(self, request, queryset):
        with transaction.atomic():
            items = list(queryset.select_for_update().filter(
                consumed_at__isnull=True, cancelled_at__isnull=True,
                blocked_at__isnull=True,
            ))
            for obj in items:
                obj.cancelled_at = timezone.now()
                obj.password_hash = "!"
                obj.save(update_fields=["cancelled_at", "password_hash"])
                self.log_change(request, obj, "Cancelou cadastro pendente; token invalidado.")
        self._report(request, len(items), queryset.count()-len(items), "cancelados")

    @admin.action(description="Bloquear cadastros pendentes (impedir novo cadastro)", permissions=["view"])
    def block_pending(self, request, queryset):
        with transaction.atomic():
            items = list(queryset.select_for_update().filter(
                consumed_at__isnull=True, blocked_at__isnull=True,
            ))
            for obj in items:
                obj.blocked_at = timezone.now()
                obj.password_hash = "!"
                obj.save(update_fields=["blocked_at", "password_hash"])
                self.log_change(request, obj, "Bloqueou cadastro pendente e novos registros dessa caixa.")
        self._report(request, len(items), queryset.count()-len(items), "bloqueados")

    @admin.action(description="Liberar bloqueio de cadastro pendente (exigir novo cadastro)", permissions=["view"])
    def unblock_pending(self, request, queryset):
        with transaction.atomic():
            items = list(queryset.select_for_update().filter(
                consumed_at__isnull=True, blocked_at__isnull=False,
            ))
            for obj in items:
                obj.blocked_at = None
                obj.cancelled_at = timezone.now()
                obj.password_hash = "!"
                obj.save(update_fields=["blocked_at", "cancelled_at", "password_hash"])
                self.log_change(request, obj, "Liberou caixa; cadastro anterior segue cancelado.")
        self._report(request, len(items), queryset.count()-len(items), "liberados para novo cadastro")

    def _confirmed_identity(self, obj):
        """Prova de correspondência: identidade confirmada + claim da caixa canônica."""
        identity = MerchantEmailIdentity.objects.select_related("user").filter(
            normalized_email=obj.normalized_email,
        ).first()
        if not identity:
            return None
        if not MerchantEmailClaim.objects.filter(
            user_id=identity.user_id,
            canonical_email=canonical_email(obj.normalized_email),
        ).exists():
            return None
        return identity

    @admin.action(description="Bloquear acesso de lojistas confirmados", permissions=["view"])
    def block_confirmed(self, request, queryset):
        changed = 0
        with transaction.atomic():
            selected = list(queryset.select_for_update().filter(
                consumed_at__isnull=False, blocked_at__isnull=True,
            ))
            for obj in selected:
                identity = self._confirmed_identity(obj)
                if not identity or not identity.user.is_active:
                    continue
                identity.user.is_active = False
                identity.user.save(update_fields=["is_active"])
                obj.blocked_at = timezone.now()
                obj.save(update_fields=["blocked_at"])
                self.log_change(request, obj, "Bloqueou acesso da conta confirmada.")
                changed += 1
        self._report(request, changed, queryset.count()-changed, "acessos bloqueados")

    @admin.action(description="Restaurar acesso bloqueado de lojistas confirmados", permissions=["view"])
    def unblock_confirmed(self, request, queryset):
        changed = 0
        with transaction.atomic():
            selected = list(queryset.select_for_update().filter(
                consumed_at__isnull=False, blocked_at__isnull=False,
            ))
            for obj in selected:
                identity = self._confirmed_identity(obj)
                if not identity or identity.user.is_active:
                    continue
                identity.user.is_active = True
                identity.user.save(update_fields=["is_active"])
                obj.blocked_at = None
                obj.save(update_fields=["blocked_at"])
                self.log_change(request, obj, "Restaurou acesso da conta confirmada.")
                changed += 1
        self._report(request, changed, queryset.count()-changed, "acessos restaurados")

    @admin.action(description="Excluir apenas cadastros NÃO confirmados e NÃO bloqueados", permissions=["view"])
    def delete_pending(self, request, queryset):
        with transaction.atomic():
            items = list(queryset.select_for_update().filter(
                consumed_at__isnull=True, blocked_at__isnull=True,
            ))
            for obj in items:
                self.log_deletion(request, obj, str(obj))
                obj.delete()
        self._report(request, len(items), queryset.count(), "excluídos")

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


@admin.register(MerchantEmailIdentity)
class MerchantEmailIdentityAdmin(admin.ModelAdmin):
    """Verifica o vínculo real da conta confirmada sem alterá-lo automaticamente."""
    list_display = ("masked_email", "verified_at", "store_links")
    search_fields = ("normalized_email", "user__username")
    list_select_related = ("user",)
    ordering = ("-verified_at",)
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "user__tenant_memberships__tenant",
        )

    @admin.display(description="E-mail confirmado")
    def masked_email(self, obj):
        try:
            local, domain = obj.normalized_email.rsplit("@", 1)
            return local[:2] + "•••@" + domain
        except ValueError:
            return "—"

    @admin.display(description="Empresas e permissões")
    def store_links(self, obj):
        memberships = list(obj.user.tenant_memberships.all())
        if not memberships:
            return "SEM VÍNCULO — revisar a empresa no Admin"
        return "; ".join(
            f"{membership.tenant.name} ({membership.get_role_display()})"
            for membership in memberships
        )

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
