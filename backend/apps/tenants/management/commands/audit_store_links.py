"""Auditoria somente leitura: contas de lojistas sem empresa, lojas sem dono.

Não associar automaticamente contas por nome, e-mail, loja homônima ou
mesmo por superusuário: a permissão deve ter prova explícita de concessão.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.models import MerchantEmailIdentity, MerchantRegistration
from apps.tenants.models import Tenant, TenantMembership


def inspect_store_links():
    """Retorna apenas contagens. Nunca expõe identificadores ou dados pessoais."""
    verified_without_store = MerchantEmailIdentity.objects.filter(
        user__tenant_memberships__isnull=True,
    ).count()
    verified_merchants = MerchantEmailIdentity.objects.count()
    stores_without_owner = Tenant.objects.annotate(
        owners=Count(
            "memberships",
            filter=Q(memberships__role=TenantMembership.Role.OWNER),
        ),
    ).filter(owners=0).count()
    staff_without_store = get_user_model().objects.filter(
        is_staff=True, tenant_memberships__isnull=True,
    ).count()
    pending_confirmations = MerchantRegistration.objects.filter(
        consumed_at__isnull=True, expires_at__gt=timezone.now(),
    ).count()
    return {
        "verified_merchants": verified_merchants,
        "verified_without_store": verified_without_store,
        "stores_without_owner": stores_without_owner,
        "staff_without_store": staff_without_store,
        "pending_confirmations": pending_confirmations,
    }


class Command(BaseCommand):
    help = "Audita vínculos entre usuários e lojas sem expor dados ou modificar o banco."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict", action="store_true",
            help="Falha quando existe um lojista com e-mail confirmado sem loja.",
        )

    def handle(self, *args, **options):
        report = inspect_store_links()
        for key, value in report.items():
            self.stdout.write(f"{key}={value}")
        self.stdout.write(
            "Nenhuma associação foi criada. Contas de staff podem ser técnicas; "
            "lojas sem dono exigem análise administrativa."
        )
        if options["strict"] and report["verified_without_store"]:
            raise CommandError(
                "Há lojista confirmado sem vínculo; revisar empresa e usuário "
                "no Admin antes de qualquer reparo."
            )
