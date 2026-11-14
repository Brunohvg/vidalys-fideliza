"""PR23 — banco PostgreSQL: o ledger não admite mutação nem via SQL cru."""
from datetime import timedelta
from unittest import skipUnless

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.points.models import PointEntry, PointEvent, PointLot, PointWallet
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEntry, CashbackEvent, CashbackWallet
from apps.wallets.services import append_cashback_event


@skipUnless(connection.vendor == "postgresql", "Triggers nativas exigem PostgreSQL")
class PostgreSQLImmutableLedgerTests(TransactionTestCase):
    def setUp(self):
        now = timezone.now()
        tenant = Tenant.objects.create(name="PG imutável", slug="pr23-immutable", status="active")
        participant = ProgramParticipant.objects.create(
            tenant=tenant, display_name="Pessoa",
            consent_at=now - timedelta(days=1), terms_version="v1",
            consent_channel="customer_portal", status="active",
        )
        wallet = PointWallet.objects.create(tenant=tenant, participant=participant)
        lot = PointLot.objects.create(
            tenant=tenant, wallet=wallet, channel="counter", source_reference="PG-IMMUTABLE-001",
            eligible_amount_cents=1000, source_paid_at=now - timedelta(minutes=5),
            verification_digest="a" * 64, rule_version="rule:1", points_issued=10,
            unlock_at=now, expires_at=now + timedelta(days=1),
        )
        event = PointEvent.objects.create(
            lot=lot, kind=PointEvent.Kind.ACCRUE,
            amount=10, idempotency_key="pg-ledger-001",
        )
        entry = PointEntry.objects.create(event=event, bucket="pending", delta=10)
        cash_wallet = CashbackWallet.objects.create(tenant=tenant, participant=participant)
        cash = CashbackEvent.objects.create(
            wallet=cash_wallet, kind="accrual", amount_cents=100,
            idempotency_key="pr23-test-accrual", source_order_id="PG-IMMUTABLE-001",
            rule_version="rule:1",
        )
        cash_entry = CashbackEntry.objects.create(event=cash, bucket="pending", delta_cents=100)
        from apps.wallets.models import CashbackOriginEntry
        origin = CashbackOriginEntry.objects.create(
            origin_event=cash, event=cash, bucket="pending", delta_cents=100,
        )
        self.table_rows = [
            ("points_pointlot", lot.pk),
            ("points_pointevent", event.pk),
            ("points_pointentry", entry.pk),
            ("wallets_cashbackevent", cash.pk),
            ("wallets_cashbackentry", cash_entry.pk),
            ("wallets_cashbackoriginentry", origin.pk),
        ]

    def test_direct_queryset_update_is_rejected(self):
        from apps.wallets.models import CashbackOriginEntry
        from django.db import models
        registry = [
            (PointLot, self.table_rows[0][1]),
            (PointEvent, self.table_rows[1][1]),
            (PointEntry, self.table_rows[2][1]),
            (CashbackEvent, self.table_rows[3][1]),
            (CashbackEntry, self.table_rows[4][1]),
            (CashbackOriginEntry, self.table_rows[5][1]),
        ]
        for model, pk in registry:
            with self.subTest(model=model.__name__), self.assertRaises(DatabaseError):
                with transaction.atomic():
                    model.objects.filter(pk=pk).update(created_at=timezone.now())

    def test_raw_sql_update_delete_are_rejected_for_all_ledger_tables(self):
        for table, pk in self.table_rows:
            for sql in (
                f"UPDATE {table} SET created_at = NOW() WHERE id = %s",
                f"DELETE FROM {table} WHERE id = %s",
            ):
                with self.subTest(table=table, sql=sql.split()[0]):
                    with self.assertRaises(DatabaseError):
                        with transaction.atomic(), connection.cursor() as cursor:
                            cursor.execute(sql, [str(pk)])
