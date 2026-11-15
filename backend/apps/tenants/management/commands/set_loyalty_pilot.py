"""Ativação explícita de um tenant piloto, sem habilitar dinheiro globalmente."""
import os
import re
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.tenants.models import Tenant, TenantLoyaltyActivationAudit


class Command(BaseCommand):
    help = "Ativa/desativa apenas loja QA isolada, com auditoria e duas confirmações."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", required=True)
        parser.add_argument("--actor-id", required=True)
        parser.add_argument("--ticket", required=True)
        parser.add_argument("--approved-sha", required=True)
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--enable", action="store_true")
        group.add_argument("--disable", action="store_true")
        parser.add_argument("--confirm", required=True)
        parser.add_argument("--mode", choices=("qa", "commercial"), default="qa")

    @transaction.atomic
    def handle(self, *args, **opts):
        mode = opts["mode"]
        if mode == "qa":
            if os.getenv("FIDELIZA_ENVIRONMENT") != "homolog":
                raise CommandError("Modo QA exclusivo de homologação")
            if os.getenv("FIDELIZA_PILOT_ACTIVATION_APPROVAL") != "YES_VERIFIED_QA_ONLY":
                raise CommandError("Aprovação do piloto QA ausente")
        else:
            if os.getenv("FIDELIZA_ENVIRONMENT") != "production":
                raise CommandError("Comercial exige ambiente production")
            if os.getenv("FIDELIZA_COMMERCIAL_ACTIVATION_APPROVAL") != "YES_COMMERCIAL_APPROVED":
                raise CommandError("Aprovação comercial formal ausente")
        if not re.fullmatch(r"[0-9a-f]{40}", opts["approved_sha"]):
            raise CommandError("Informe SHA completo aprovado")
        deployed = os.getenv("FIDELIZA_DEPLOYED_SHA", "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", deployed) or deployed != opts["approved_sha"]:
            raise CommandError("SHA aprovado difere do commit efetivamente publicado")
        if not re.fullmatch(r"[A-Za-z0-9._-]{6,100}", opts["ticket"]):
            raise CommandError("Ticket de aprovação inválido")
        confirmation = ("ENABLE_QA_ONLY" if opts["enable"] else "DISABLE_QA_ONLY") if mode == "qa" else (
            "ENABLE_COMMERCIAL" if opts["enable"] else "DISABLE_COMMERCIAL"
        )
        if opts["confirm"] != confirmation:
            raise CommandError("Confirmação de operação incorreta")
        try:
            tid = uuid.UUID(opts["tenant_id"])
            actor_id = get_user_model()._meta.pk.to_python(opts["actor_id"])
        except (TypeError, ValueError, AttributeError):
            raise CommandError("UUID inválido") from None
        actor = get_user_model().objects.filter(pk=actor_id, is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("Operador precisa ser superusuário Django autorizado")
        tenant = Tenant.objects.select_for_update().filter(pk=tid).first()
        if tenant is None:
            raise CommandError("Tenant não encontrado")
        if mode == "qa" and not re.fullmatch(r"(qa|homolog)-[a-z0-9-]{3,52}", tenant.slug):
            raise CommandError("Modo QA exige loja explicitamente de QA")
        if mode == "qa" and "bibel" in tenant.name.casefold():
            raise CommandError("Loja Bibelô fora do escopo QA")
        if opts["enable"] and tenant.status != Tenant.Status.ACTIVE:
            raise CommandError("Tenant QA deve estar ativo")
        if mode == "qa" and opts["enable"] and (
            settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
            or settings.FIDELIZA_LEDGER_WRITES_ENABLED
            or settings.FIDELIZA_POINTS_WRITES_ENABLED
            or getattr(settings, "FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED", False)
        ):
            raise CommandError("Piloto QA preparatório deve manter dinheiro e cupons externos desligados")
        gates_digest = ""
        if mode == "commercial" and opts["enable"]:
            from apps.tenants.commercial_gates import CommercialGateBlocked, commercial_readiness
            try:
                gates_digest = commercial_readiness(tenant=tenant, check_live_get=True)
            except CommercialGateBlocked:
                raise CommandError("Go-Live NO-GO: prova técnica de pagamento/checkout incompleta.") from None
        enabled = bool(opts["enable"])
        if not enabled:
            from apps.nuvemshop.models import NuvemshopCouponIntent
            if NuvemshopCouponIntent.objects.filter(
                tenant=tenant, state__in=(
                    NuvemshopCouponIntent.State.UNCERTAIN,
                    NuvemshopCouponIntent.State.ISSUED,
                    NuvemshopCouponIntent.State.APPLIED,
                    NuvemshopCouponIntent.State.REVOKING,
                    NuvemshopCouponIntent.State.REVOKE_UNKNOWN,
                ),
            ).exists():
                raise CommandError("Cupom externo pendente: revogue/confira antes de desativar.")
        if tenant.loyalty_live_enabled == enabled:
            self.stdout.write("SEM_ALTERACAO tenant já possui estado solicitado")
            return
        before = tenant.loyalty_live_enabled
        tenant.loyalty_live_enabled = enabled
        tenant.save(update_fields=["loyalty_live_enabled"])
        TenantLoyaltyActivationAudit.objects.create(
            tenant=tenant, actor=actor, before_enabled=before, after_enabled=enabled,
            approved_sha=opts["approved_sha"], ticket=opts["ticket"],
            mode=mode, gates_digest=gates_digest,
        )
        self.stdout.write("LOYALTY_STATE_CHANGED mode=" + mode + " gate_audited=YES")
