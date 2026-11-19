"""Muda o modo de operação de UMA loja (teste <-> comercial). Só superusuário, com confirmação.

Uso no servidor (Coolify → serviço api → Terminal):
    python manage.py set_store_operation --tenant <slug> --mode commercial --actor <usuario> --confirm COMMERCIAL
    python manage.py set_store_operation --tenant <slug> --mode test --actor <usuario> --confirm TEST

O comercial só é aceito com os requisitos de pé (regulamento, regra, canais do site).
Voltar para teste é sempre aceito e reaplica os tetos baixos na hora.
"""
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.sales.models import CounterPilot
from apps.sales.policy import COMMERCIAL, TEST, blockers
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Define o modo de operação do clube de uma loja: test ou commercial."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug da loja")
        parser.add_argument("--mode", required=True, choices=[TEST, COMMERCIAL])
        parser.add_argument("--actor", required=True, help="usuário superusuário que aprova")
        parser.add_argument("--confirm", required=True, help="COMMERCIAL ou TEST, igual ao modo")

    @transaction.atomic
    def handle(self, *args, **opts):
        mode = opts["mode"]
        if opts["confirm"] != mode.upper():
            raise CommandError(f"Confirmação incorreta: use --confirm {mode.upper()}")
        actor = get_user_model().objects.filter(username=opts["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("Quem aprova precisa ser superusuário ativo.")
        tenant = Tenant.objects.select_for_update().filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError("Loja não encontrada.")
        pilot = CounterPilot.objects.select_for_update().filter(tenant=tenant).first()
        if pilot is None:
            raise CommandError("A loja ainda não configurou o clube (Meu clube → Ativar).")
        previous = (pilot.operation_mode, pilot.commercial_at, pilot.commercial_by_id)
        if mode == COMMERCIAL:
            pilot.operation_mode, pilot.commercial_at, pilot.commercial_by = COMMERCIAL, timezone.now(), actor
            missing = blockers(pilot)
            if missing:
                raise CommandError("Faltam requisitos para o modo comercial:\n- " + "\n- ".join(missing))
        else:
            pilot.operation_mode, pilot.commercial_at, pilot.commercial_by = TEST, None, None
        pilot.save(update_fields=["operation_mode", "commercial_at", "commercial_by", "updated_at"])
        logger.warning("store_operation tenant=%s from=%s to=%s actor=%s", tenant.pk, previous[0], mode, actor.pk)
        self.stdout.write(self.style.SUCCESS(f"{tenant.slug}: modo {mode}."))
