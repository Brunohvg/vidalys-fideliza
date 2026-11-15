"""PR30 verified fee mapping, cursor completeness and negative settlement cases."""
from django.test import SimpleTestCase
from apps.nuvemshop.pagarme_payment import PaymentProviderError
from apps.nuvemshop.pagarme_payables import fetch_payables, verify_payables


class FakeResponse:
    status = 200
    def __init__(self, payload):
        import json
        self.body=json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self, n):
        return self.body[:n]


class Opener:
    def __init__(self, *pages):
        self.pages=list(pages)
        self.requested=[]
    def open(self, request, timeout=8):
        self.requested.append(request.full_url)
        return FakeResponse(self.pages.pop(0))


class PagarmeFeeContractTests(SimpleTestCase):
    def setUp(self):
        self.charge="ch_ABC123456789"
        self.recipient="re_ABC123456789"
        self.paid={
            "id":199,"charge_id":self.charge,"recipient_id":self.recipient,
            "status":"paid","type":"credit","amount":2990,
            "fee":80,"anticipation_fee":5,"fraud_coverage_fee":15,
            "split_id":None,"originator_model":None,
        }

    def test_paginated_authenticated_get_does_not_hide_non_credit_events(self):
        opener=Opener(
            {"data":[self.paid],"paging":{"forward_cursor":"cursor-1"}},
            {"data":[],"paging":{"forward_cursor":None}},
        )
        result=fetch_payables(
            charge_id=self.charge,
            secret_key="sk_test_" + "x"*28,
            opener=opener,
        )
        self.assertEqual(result,[self.paid])
        self.assertIn("charge_id=ch_ABC",opener.requested[0])
        self.assertIn("forward_cursor=cursor-1",opener.requested[1])
        self.assertNotIn("type=credit",opener.requested[0])

    def test_fee_and_net_are_exact_cents_and_mutations_rejected(self):
        actual=verify_payables(
            payables=[self.paid],charge_id=self.charge,
            captured_cents=2990,recipient_id=self.recipient,
        )
        self.assertEqual(actual.gross_cents,2990)
        self.assertEqual(actual.fee_cents,100)
        self.assertEqual(actual.net_cents,2890)
        self.assertEqual(len(actual.snapshot_digest),64)
        for patch in (
            {"recipient_id":"re_FOREIGN12345"},
            {"fee":None},
            {"anticipation_fee":None},
            {"fraud_coverage_fee":None},
            {"charge_id":"ch_other12345678"},
            {"type":"chargeback"},
            {"status":"waiting_funds"},
            {"split_id":"split-other"},
            {"amount":2991},
        ):
            with self.subTest(patch=patch),self.assertRaises(PaymentProviderError):
                verify_payables(payables=[{**self.paid,**patch}],
                                charge_id=self.charge,captured_cents=2990,
                                recipient_id=self.recipient)
        for group in (
            [self.paid,self.paid],
            [{**self.paid,"id":88,"type":"refund"}],
        ):
            with self.assertRaises(PaymentProviderError):
                verify_payables(payables=group,
                                charge_id=self.charge,captured_cents=2990,
                                recipient_id=self.recipient)

    def test_missing_or_looped_pagination_is_not_considered_complete(self):
        with self.assertRaises(PaymentProviderError):
            fetch_payables(
                charge_id=self.charge,
                secret_key="sk_test_" + "x"*28,
                opener=Opener(
                    {"data":[self.paid],"paging":{"forward_cursor":"A"}},
                    {"data":[self.paid],"paging":{"forward_cursor":"A"}},
                ),
            )
        with self.assertRaises(PaymentProviderError):
            fetch_payables(
                charge_id=self.charge,
                secret_key="sk_test_" + "x"*28,
                opener=Opener({"data":[self.paid]}),
            )
