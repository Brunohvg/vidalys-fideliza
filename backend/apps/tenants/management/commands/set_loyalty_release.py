"""PR26: release command with separate QA and commercial gates, fail closed.

Cannot enable real commerce with the current hardcoded financial flags OFF.
Business approval alone never overrides PSP, OAuth or PostgreSQL checks.
"""
import os
import re
import uuid
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.costs.catalog_gate import verify_active_catalog_costs, CatalogCostCoverageBlocked
from apps.loyalty.models import LoyaltyRule, LoyaltyTier
from apps.nuvemshop.models import NuvemshopInstallation, NuvemshopCouponIntent
from apps.nuvemshop.order_readonly import read_orders_page, OrderReadError
from apps.nuvemshop.scopes import parse_scopes
from apps.nuvemshop.security import config, decrypt_token
from apps.tenants.models import Tenant, TenantLoyaltyActivationAudit
from apps.tenants.management.commands.set_loyalty_pilot import qa_scope_authorized


REQUIRED_TRIGGERS = (
    "points_pointlot", "points_pointevent", "points_pointentry",
    "wallets_cashbackevent", "wallets_cashbackentry", "wallets_cashbackoriginentry",
    "loyalty_financialevidence", "loyalty_verifiedpaymentproof",
    "loyalty_cashclosing", "loyalty_verifiedpspfeereceipt",
    "nuvemshop_nuvemshopcouponrevocationaudit",
)


def verify_postgres_immutability():
    if connection.vendor != "postgresql":
        raise CommandError("Go-Live exige PostgreSQL real com triggers")
    with connection.cursor() as cur:
        for table in REQUIRED_TRIGGERS:
            cur.execute("""
                SELECT t.tgenabled, t.tgtype, pg_get_userbyid(c.relowner)
                FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                WHERE t.tgrelid=to_regclass(%s) AND t.tgname=%s
                  AND NOT t.tgisinternal
            """, ["public." + table, table + "_immutable"])
            rows=cur.fetchall()
            if len(rows)!=1 or rows[0][0] not in ("O","A") or rows[0][1]&27 != 27:
                raise CommandError("Trigger financeiro obrigatório ausente: " + table)
            if rows[0][2] == connection.settings_dict["USER"]:
                raise CommandError("Role de runtime não pode possuir a tabela: "+table)
            cur.execute("SELECT has_table_privilege(current_user, %s, 'TRUNCATE')",
                        ["public." + table])
            if cur.fetchone()[0]:
                raise CommandError("Role runtime com TRUNCATE sobre ledger: "+table)
        cur.execute("SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated")
        if cur.fetchone()[0]:
            raise CommandError("Foreign keys não validadas")


def check_rule_and_costs(tenant):
    rule=LoyaltyRule.objects.filter(tenant=tenant,enabled=True).first()
    if (rule is None or rule.budget_cents <= 0
            or not 0 <= rule.minimum_margin_bps <= 10000
            or not LoyaltyTier.objects.filter(rule=rule,minimum_spend_cents=0).exists()):
        raise CommandError("Sem regra, nível inicial ou orçamento do programa")


def check_oauth(tenant):
    if tenant.platform != "nuvemshop" or not tenant.external_store_id:
        raise CommandError("Ativação comercial inicial exige loja Nuvemshop")
    cfg=config()
    installed=NuvemshopInstallation.objects.filter(
        tenant=tenant,store_id=tenant.external_store_id,
        client_id=cfg.client_id,
    ).first()
    if installed is None or not {
        "read_orders", "write_coupons", "read_products",
    } <= parse_scopes(installed.scope):
        raise CommandError("OAuth precisa de read_orders, read_products e write_coupons")
    token=decrypt_token(installed.token_ciphertext,cfg.token_keys)
    try:
        read_orders_page(
            store_id=installed.store_id,
            access_token=token,user_agent=cfg.user_agent,
        )
    except OrderReadError:
        raise CommandError("GET OAuth atual não foi validado") from None
    return installed.store_id, token, cfg.user_agent


class Command(BaseCommand):
    help="Gerencia flag por loja com gates explícitos QA ou commercial."

    def add_arguments(self,parser):
        parser.add_argument("--mode",choices=("qa","commercial"),required=True)
        parser.add_argument("--tenant-id",required=True)
        parser.add_argument("--actor-id",required=True)
        parser.add_argument("--ticket",required=True)
        parser.add_argument("--approved-sha",required=True)
        parser.add_argument("--dry-run",action="store_true",help="Prontidão sem alterar flag ou emitir cupom")
        group=parser.add_mutually_exclusive_group(required=False)
        group.add_argument("--enable",action="store_true")
        group.add_argument("--disable",action="store_true")
        parser.add_argument("--confirm",required=True)

    def handle(self,*args,**opts):
        mode=opts["mode"]
        if opts["dry_run"]:
            if opts["enable"] or opts["disable"]:
                raise CommandError("Dry-run não pode acompanhar --enable/--disable")
            try:
                tenant_id=uuid.UUID(opts["tenant_id"])
            except (ValueError,TypeError):
                raise CommandError("Identificador da loja inválido") from None
            tenant=Tenant.objects.filter(pk=tenant_id).first()
            if tenant is None:
                raise CommandError("Loja não localizada")
            # No write, no HTTP GET, no deployment and no live activation.
            rule_ok=LoyaltyRule.objects.filter(
                tenant=tenant,enabled=True,
            ).exists()
            installation_ok=NuvemshopInstallation.objects.filter(
                tenant=tenant,store_id=tenant.external_store_id,
            ).exists()
            # O programa é multicanal: um lojista pode validar adesão,
            # regulamento e recompensas sem instalar a Nuvemshop.
            # O gate comercial continua separado, exigindo PSP e checkout.
            from apps.sales.models import PointRuleDraft
            rule_draft_ok = PointRuleDraft.objects.filter(tenant=tenant).exists()
            qa_namespace_ok = bool(re.fullmatch(
                r"(qa|homolog)-[a-z0-9-]{3,52}", tenant.slug,
            ))
            qa_scope_ok = qa_scope_authorized(tenant)
            financial_gates_off = not any((
                settings.FIDELIZA_POINTS_WRITES_ENABLED,
                settings.FIDELIZA_LEDGER_WRITES_ENABLED,
                settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED,
                getattr(settings, "FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED", False),
            ))
            qa_environment_ok = os.getenv("FIDELIZA_ENVIRONMENT") == "homolog"
            qa_approval_ok = (
                os.getenv("FIDELIZA_PILOT_ACTIVATION_APPROVAL")
                == "YES_VERIFIED_QA_ONLY"
            )
            qa_ready = bool(
                tenant.status == Tenant.Status.ACTIVE
                and qa_scope_ok and qa_environment_ok and qa_approval_ok
                and financial_gates_off and not tenant.loyalty_live_enabled
            )
            commercial_preview_ready = bool(
                tenant.status == Tenant.Status.ACTIVE
                and tenant.platform == "nuvemshop"
                and tenant.external_store_id and rule_ok and installation_ok
                and not tenant.loyalty_live_enabled
            )
            program_ready = (
                qa_ready if mode == "qa" else commercial_preview_ready
            )
            gates={
                "tenant_active":tenant.status==Tenant.Status.ACTIVE,
                "tenant_live_disabled":not tenant.loyalty_live_enabled,
                "platform":tenant.platform,
                "qa_namespace_valid":qa_namespace_ok,
                "qa_scope_authorized":qa_scope_ok,
                "qa_environment":qa_environment_ok,
                "qa_approval_configured":qa_approval_ok,
                "financial_gates_off":financial_gates_off,
                "point_rule_draft_configured":rule_draft_ok,
                "rule_configured":rule_ok,
                "oauth_installed":installation_ok,
                "oauth_optional_for_independent_qa":tenant.platform=="independent",
                "checkout_preventive_verified":
                    settings.FIDELIZA_CHECKOUT_OWNER_ENFORCEMENT_VERIFIED,
                "sku_line_binding_verified":
                    settings.FIDELIZA_ORDER_LINE_COST_BINDING_VERIFIED,
                "psp_fee_reconciliation_verified":
                    settings.FIDELIZA_PSP_FEE_RECONCILIATION_VERIFIED,
                "psp_recording_enabled":
                    settings.FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED,
            }
            report={
                "status":("READY_FOR_HOMOLOG_ACTIVATION" if program_ready else
                          "NOT_READY_FOR_HOMOLOG_ACTIVATION"),
                "commercial_status":"NO_GO_COMMERCIAL",
                "mode":mode,
                "dry_run":True,"tenant_id":str(tenant.pk),
                "loyalty_live_enabled":tenant.loyalty_live_enabled,
                "checks":gates,
                "note":"Pré-voo sem escrita/HTTP. Modo QA libera apenas preparação local; não concede pontos nem cupons. PSP, custos e checkout exigem prova para uso comercial.",
            }
            self.stdout.write(json.dumps(report,sort_keys=True,ensure_ascii=False))
            return
        if not opts["enable"] and not opts["disable"]:
            raise CommandError("Exige --enable, --disable ou --dry-run")
        if mode=="qa":
            call_command(
                "set_loyalty_pilot",
                tenant_id=opts["tenant_id"],actor_id=opts["actor_id"],
                ticket=opts["ticket"],approved_sha=opts["approved_sha"],
                enable=opts["enable"],disable=opts["disable"],
                confirm=opts["confirm"],
            )
            return
        if os.getenv("FIDELIZA_ENVIRONMENT")!="production":
            raise CommandError("Modo comercial exige ambiente production")
        if os.getenv("FIDELIZA_COMMERCIAL_GO_LIVE_APPROVED")!="YES_RELEASE_REVIEWED":
            raise CommandError("Aprovação comercial ausente")
        if opts["confirm"]!=("ENABLE_COMMERCIAL" if opts["enable"] else "DISABLE_COMMERCIAL"):
            raise CommandError("Confirmação de operação divergente")
        if (not re.fullmatch("[0-9a-f]{40}",opts["approved_sha"])
                or opts["approved_sha"] != os.getenv("FIDELIZA_DEPLOYED_SHA")):
            raise CommandError("Commit de release não confirmado")
        if not re.fullmatch("[A-Za-z0-9._-]{6,100}",opts["ticket"]):
            raise CommandError("Ticket inválido")
        try:
            tid=uuid.UUID(opts["tenant_id"])
            actor_pk=get_user_model()._meta.pk.to_python(opts["actor_id"])
        except (ValueError,TypeError):
            raise CommandError("Identificadores inválidos") from None
        if str(tid)!=os.getenv("FIDELIZA_COMMERCIAL_ALLOWED_TENANT_ID",""):
            raise CommandError("Loja comercial não pertence à aprovação")
        actor=get_user_model().objects.filter(
            pk=actor_pk,is_superuser=True,is_active=True,
        ).first()
        if actor is None:
            raise CommandError("Operador comercial não autorizado")
        # A desativação administrativa continua possível somente se os cupons
        # pendentes foram reconciliados; não elimina saldos financeiros.
        if opts["enable"]:
            if not (settings.FIDELIZA_POINTS_WRITES_ENABLED
                    and settings.FIDELIZA_LEDGER_WRITES_ENABLED
                    and settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
                    and settings.FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED
                    and settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS
                    and settings.FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED
                    and settings.FIDELIZA_CHECKOUT_OWNER_ENFORCEMENT_VERIFIED
                    and settings.FIDELIZA_PREISSUE_OWNERSHIP_CHECK_ENABLED
                    and settings.FIDELIZA_ORDER_LINE_COST_BINDING_VERIFIED
                    and settings.FIDELIZA_PSP_FEE_RECONCILIATION_VERIFIED
                    and "pagarme_v5" in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS):
                raise CommandError("Flags financeiras/PSP não homologadas: NO-GO")
            verify_postgres_immutability()
        # Run remote network preflight BEFORE taking an exclusive tenant lock.
        # Recheck the local rule and tenant identity under the final lock.
        inspected_store_id = None
        if opts["enable"]:
            inspected = Tenant.objects.filter(pk=tid, status=Tenant.Status.ACTIVE).first()
            if inspected is None:
                raise CommandError("Loja comercial não ativa")
            check_rule_and_costs(inspected)
            store_id, token, user_agent = check_oauth(inspected)
            try:
                verify_active_catalog_costs(
                    tenant=inspected, store_id=store_id,
                    token=token, user_agent=user_agent,
                )
            except CatalogCostCoverageBlocked as exc:
                raise CommandError(str(exc)) from None
            inspected_store_id = store_id
        with transaction.atomic():
            tenant=Tenant.objects.select_for_update().filter(pk=tid).first()
            if tenant is None or tenant.status!=Tenant.Status.ACTIVE:
                raise CommandError("Loja comercial não ativa")
            if opts["enable"]:
                if tenant.external_store_id != inspected_store_id:
                    raise CommandError("Loja mudou durante a auditoria do catálogo")
                check_rule_and_costs(tenant)
            elif NuvemshopCouponIntent.objects.filter(
                tenant=tenant,
                state__in=[
                    NuvemshopCouponIntent.State.ISSUED,
                    NuvemshopCouponIntent.State.APPLIED,
                    NuvemshopCouponIntent.State.UNCERTAIN,
                    NuvemshopCouponIntent.State.REVOKING,
                    NuvemshopCouponIntent.State.OWNERSHIP_VIOLATION,
                ],
            ).exists():
                raise CommandError("Há cupons externos pendentes: primeiro conciliar")
            intended=bool(opts["enable"])
            if tenant.loyalty_live_enabled==intended:
                self.stdout.write("SEM_ALTERACAO")
                return
            before=tenant.loyalty_live_enabled
            tenant.loyalty_live_enabled=intended
            tenant.save(update_fields=["loyalty_live_enabled"])
            TenantLoyaltyActivationAudit.objects.create(
                tenant=tenant,actor=actor,before_enabled=before,
                after_enabled=intended,approved_sha=opts["approved_sha"],
                ticket=opts["ticket"],
            )
        self.stdout.write("COMMERCIAL_FLAG_UPDATED AUDIT_RECORDED")
