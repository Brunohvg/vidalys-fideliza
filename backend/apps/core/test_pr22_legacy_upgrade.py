"""PR22: a partir do esquema real legado, testar upgrade sem perder linhas.

Executa somente em test DB descartável. Nunca altera banco homolog/produção.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class LegacySchemaUpgradeSmokeTests(TransactionTestCase):
    """Migração incremental de Sales 0003, sem PR19-21 aplicado previamente."""

    def test_legacy_sale_and_participant_survive_incremental_upgrade(self):
        executor = MigrationExecutor(connection)
        final_targets = executor.loader.graph.leaf_nodes()
        old_targets = [
            ("sales", "0003_reward_publication"),
            ("customers", None),
            ("channels", None),
            ("loyalty", None),
        ]
        try:
            executor.migrate(old_targets)
            old = executor.loader.project_state([("sales", "0003_reward_publication")]).apps
            Tenant = old.get_model("tenants", "Tenant")
            Participant = old.get_model("participants", "ProgramParticipant")
            Sale = old.get_model("sales", "SaleRecord")
            User = old.get_model("auth", "User")
            owner = User.objects.create(username="pr22-legacy-owner")
            tenant = Tenant.objects.create(
                name="Loja legada sintética", slug="pr22-legacy-store",
                status="active", platform="independent",
            )
            member = Participant.objects.create(
                tenant=tenant, external_customer_id="legacy-customer-01",
                display_name="Participante legado",
                contact_email="legacy@example.invalid", consent_at=timezone.now(),
                consent_channel="customer_portal", terms_version="v1", status="active",
            )
            sale = Sale.objects.create(
                tenant=tenant, participant=member, submitted_by=owner,
                channel="counter", external_reference="LEGACY-CUPOM-001",
                eligible_amount_cents=12990, currency="BRL",
                reported_paid_at=timezone.now(), evidence_reference="LEGACY-CUPOM-001",
                state="verified_manual",
            )
            member_id, sale_id, tenant_id = member.pk, sale.pk, tenant.pk
            executor = MigrationExecutor(connection)
            executor.migrate(final_targets)
            from apps.participants.models import ProgramParticipant
            from apps.sales.models import SaleRecord, SaleEventReceipt
            from apps.customers.models import CustomerProfile
            from apps.loyalty.models import LoyaltyGrant
            from apps.points.models import PointEntry
            from apps.wallets.models import CashbackEntry

            preserved = SaleRecord.objects.get(pk=sale_id)
            self.assertEqual(preserved.tenant_id, tenant_id)
            self.assertEqual(preserved.participant_id, member_id)
            self.assertEqual(preserved.eligible_amount_cents, 12990)
            self.assertEqual(preserved.external_reference, "LEGACY-CUPOM-001")
            self.assertEqual(preserved.state, "verified_manual")
            self.assertEqual(preserved.order_status, "pending")
            self.assertEqual(preserved.reported_total_cents, 0)
            self.assertIsNone(preserved.customer_profile_id)
            self.assertEqual(ProgramParticipant.objects.get(pk=member_id).external_customer_id,
                             "legacy-customer-01")
            self.assertFalse(CustomerProfile.objects.exists())
            self.assertFalse(SaleEventReceipt.objects.exists())
            self.assertFalse(LoyaltyGrant.objects.exists())
            self.assertFalse(PointEntry.objects.exists())
            self.assertFalse(CashbackEntry.objects.exists())
        finally:
            # Mesmo no fracasso, restaurar esquema de testes ao estado atual.
            new_executor = MigrationExecutor(connection)
            new_executor.migrate(final_targets)
