"""Corridas reais com PostgreSQL (no SQLite os locks não existem: estes testes são pulados).

Duas threads, cada uma com sua conexão, disparam juntas (Barrier) a mesma operação:
gerar cupom, processar o mesmo pedido pago, e gastar o mesmo saldo no ledger.
A Nuvemshop é simulada; o banco é real. Roda no job `backend_postgres` do CI.
"""
import threading
import time
from unittest import mock, skipUnless

from django.db import connection
from django.db.models import Sum
from django.test import TransactionTestCase, override_settings

from apps.points.models import PointEvent, PointLot
from apps.points.services import transition_points
from .models import OnlineCoupon
from .online import issue_coupon
from .pilot import wallet_balances
from .test_online_redemption import FLAGS, StoreFixture


def slow_remote(coupon, opener=None):
    time.sleep(0.3)                     # alarga a janela da corrida
    return "777", "https://loja.example/discount/X"


@skipUnless(connection.vendor == "postgresql", "corridas reais só com PostgreSQL")
@override_settings(**FLAGS)
class PostgresRaceTests(StoreFixture, TransactionTestCase):
    def race(self, fn, n=2):
        barrier, results = threading.Barrier(n), []

        def run():
            try:
                barrier.wait(timeout=10)
                results.append(fn())
            except Exception as exc:     # o resultado de cada thread é conferido abaixo
                results.append(exc)
            finally:
                connection.close()
        threads = [threading.Thread(target=run) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return results

    def test_two_clicks_at_once_reserve_credit_once(self):
        self.paid("9001", 15776)
        with mock.patch("apps.sales.online._create_remote", side_effect=slow_remote):
            self.race(lambda: issue_coupon(self.ana))
        self.assertEqual(OnlineCoupon.objects.exclude(state="failed").count(), 1)
        self.assertEqual(wallet_balances(self.ana)[1]["reserved"], 1577)
        self.assertEqual(wallet_balances(self.ana)[1]["available"], 0)

    def test_same_paid_order_twice_at_once_redeems_and_grants_once(self):
        self.paid("9001", 10000)
        with mock.patch("apps.sales.online._create_remote", side_effect=slow_remote):
            coupon = issue_coupon(self.ana)
        results = self.race(lambda: self.paid("9500", 12000, codes=[coupon.code]))
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(sum("coupon_used" in r for r in results), 1)
        self.assertEqual(PointEvent.objects.filter(kind="redeem").aggregate(t=Sum("amount"))["t"], 1000)
        self.assertEqual(PointLot.objects.filter(source_reference="site:9500").count(), 1)

    def test_ledger_never_spends_the_same_balance_twice(self):
        self.paid("9001", 10000)
        from .pilot import release_due
        release_due(PointLot.objects.get(source_reference="site:9001").wallet)
        lot = PointLot.objects.get(source_reference="site:9001")
        keys = iter(["race-a:1", "race-b:1"])
        results = self.race(lambda: transition_points(lot_id=lot.pk, kind=PointEvent.Kind.RESERVE,
                                                      amount=1000, idempotency_key=next(keys)))
        self.assertEqual(sum(isinstance(r, ValueError) for r in results), 1)   # um ganha, outro sem saldo
        self.assertEqual(wallet_balances(self.ana)[1], {"pending": 0, "available": 0, "reserved": 1000})
