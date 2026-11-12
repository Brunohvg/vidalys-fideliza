"""G7: verificação financeira pura sem banco, HTTP ou credenciais reais."""
from dataclasses import replace

from django.test import SimpleTestCase

from .order_readonly import summarize_order
from .payment_reconciliation import (
    MAX_EVENTS, PaymentFact, PaymentReconciliationError, reconcile_payment_facts,
)


class PaymentReconciliationTests(SimpleTestCase):
    def snapshot(self, **changes):
        order = {
            "id": 87412, "status": "open", "payment_status": "paid",
            "paid_at": "2026-11-11T10:00:00+00:00",
            "cancelled_at": None, "total": "120.90",
            "total_paid_by_customer": "120.90",
            "currency": "BRL", "gateway": "mercadopago",
        }
        order.update(changes)
        return summarize_order(order, order_id=87412, participant_verified=True)

    def fact(self, **changes):
        base = {
            "tenant_id": "tenant-a", "store_id": "54321",
            "order_id": "87412", "provider": "psp-synthetic",
            "event_id": "event-capture", "transaction_id": "tx-capture",
            "kind": "capture", "amount_cents": 12090,
        }
        base.update(changes)
        return PaymentFact(**base)

    def run_report(self, facts, snapshot=None):
        return reconcile_payment_facts(
            self.snapshot() if snapshot is None else snapshot,
            facts, tenant_id="tenant-a", store_id="54321",
        )

    def test_exact_payment_still_cannot_release_cashback(self):
        result = self.run_report([self.fact()])
        self.assertEqual(result["captured_cents"], 12090)
        self.assertEqual(result["net_cents"], 12090)
        self.assertEqual(result["review_status"], "amounts_match_but_provider_not_authenticated")
        self.assertFalse(result["independent_psp_proof_verified"])
        self.assertFalse(result["payment_eligible_for_rewards"])
        self.assertFalse(result["credit_eligible"])
        self.assertFalse(result["cashback_created"])
        self.assertEqual(result["ledger_writes_performed"], 0)
        self.assertTrue(result["requires_margin_and_campaign_budget_validation"])

    def test_duplicate_delivery_does_not_duplicate_payment(self):
        original = self.fact()
        report = self.run_report([original, original, original])
        self.assertEqual(report["unique_financial_events"], 1)
        self.assertEqual(report["duplicate_deliveries_ignored"], 2)
        self.assertEqual(report["captured_cents"], 12090)
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([original, replace(original, amount_cents=9000)])
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([
                original, replace(original, event_id="another-capture-event"),
            ])

    def test_split_capture_and_partial_payment(self):
        a = self.fact(amount_cents=8000)
        b = self.fact(event_id="event-capture-2", transaction_id="tx-2",
                      amount_cents=4090)
        report = self.run_report([b, a])
        self.assertEqual(report["captured_cents"], 12090)
        self.assertEqual(report["review_status"], "amounts_match_but_provider_not_authenticated")
        partial = self.run_report([a])
        self.assertEqual(partial["review_status"], "capture_total_mismatch")
        self.assertEqual(partial["captured_cents"], 8000)

    def test_refund_chargeback_and_out_of_order_events_block(self):
        c = self.fact()
        refund = self.fact(
            event_id="event-refund", transaction_id="tx-refund",
            kind="refund", amount_cents=2090, original_capture_id="tx-capture",
        )
        chargeback = self.fact(
            event_id="event-dispute", transaction_id="tx-dispute",
            kind="chargeback", amount_cents=5000, original_capture_id="tx-capture",
        )
        result = self.run_report([refund, c, refund])
        self.assertEqual(result["review_status"], "refund_review")
        self.assertEqual(result["net_cents"], 10000)
        self.assertEqual(result["duplicate_deliveries_ignored"], 1)
        result = self.run_report([chargeback, c, refund])
        self.assertEqual(result["review_status"], "chargeback_review")
        self.assertEqual(result["net_cents"], 5000)
        for malformed in (
            self.fact(event_id="evt", transaction_id="tx", kind="refund",
                      amount_cents=1, original_capture_id="other-tx"),
            self.fact(event_id="evt", transaction_id="tx", kind="chargeback",
                      amount_cents=1, original_capture_id="other-tx"),
        ):
            with self.assertRaises(PaymentReconciliationError):
                self.run_report([c, malformed])
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([c, replace(refund, amount_cents=13000)])
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([
                c, refund,
                replace(refund, event_id="another-event-same-refund-operation"),
            ])
        # Mesmo com duas capturas, a soma de reversões não pode exceder
        # a transação original, ainda que fique abaixo do total geral.
        second = self.fact(event_id="capture-2", transaction_id="tx-2",
                           amount_cents=3000)
        first = self.fact(amount_cents=9090)
        bad_refund = replace(
            refund, amount_cents=10000,
        )
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([second, first, bad_refund])

    def test_platform_disagreements_identity_and_manual_payment(self):
        self.assertEqual(self.run_report([], self.snapshot())["review_status"],
                         "no_independent_payment_facts")
        self.assertEqual(self.run_report([self.fact()],
            self.snapshot(total_paid_by_customer="110.90"))["review_status"],
            "platform_paid_amount_mismatch")
        self.assertEqual(self.run_report([self.fact()],
            self.snapshot(total_paid_by_customer=None))["review_status"],
            "platform_paid_amount_missing")
        self.assertEqual(self.run_report([self.fact()],
            self.snapshot(gateway="internal"))["review_status"],
            "manual_payment_review")
        self.assertEqual(self.run_report([self.fact()],
            self.snapshot(payment_status="pending"))["review_status"],
            "platform_payment_not_paid")
        unverified = self.snapshot()
        unverified["participant_verified"] = False
        self.assertEqual(self.run_report([self.fact()], unverified)["review_status"],
                         "participant_not_verified")
        self.assertEqual(self.run_report([self.fact()],
            self.snapshot(status="cancelled"))["review_status"],
            "order_cancelled_or_refunded")
        self.assertEqual(self.run_report([self.fact()],
            self.snapshot(payment_status="refunded"))["review_status"],
            "order_cancelled_or_refunded")

    def test_scoping_type_validation_and_closed_outcomes(self):
        c = self.fact()
        for changed in (
            {"tenant_id": "tenant-b"}, {"store_id": "another-store"},
            {"order_id": "11111"}, {"currency": "USD"},
            {"provider": "PSP Bad"}, {"event_id": "has spaces"},
            {"amount_cents": True}, {"amount_cents": 0},
            {"kind": "authorized"}, {"kind": "capture", "original_capture_id": "tx"},
        ):
            with self.subTest(changed=changed), self.assertRaises(PaymentReconciliationError):
                self.run_report([replace(c, **changed)])
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([{"kind": "capture", "amount_cents": 12090}])
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([c] * (MAX_EVENTS + 1))
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([c], {"order_id": "87412"})
        snapshot = self.snapshot()
        snapshot["currency"] = "USD"
        with self.assertRaises(PaymentReconciliationError):
            self.run_report([c], snapshot)
