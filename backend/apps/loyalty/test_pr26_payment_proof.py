"""PR26: independent PSP/PDV proof, strict buyer, remote DELETE compensation.

All network responses are synthetic. No merchant keys, no live store writes.
"""
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from apps.loyalty.models import FinancialEvidence, VerifiedPaymentProof, CashClosing
from apps.loyalty.payment_proof import (
    confirm_pagarme_charge, attest_cash_close, PaymentProofBlocked,
)
from apps.nuvemshop.pagarme_payment import PaymentProviderError, validate_paid_charge
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant, TenantMembership


class FakeResponse:
    status = 200
    def __init__(self, payload):
        import json
        self.payload = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self, size):
        return self.payload[:size]


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.last = None
    def open(self, request, timeout=8):
        self.last = request
        return FakeResponse(self.payload)


class PagarmeContractTests(SimpleTestCase):
    def test_charge_mapping_requires_paid_order_amount_and_timestamp(self):
        when = timezone.now().isoformat()
        data = {"id":"ch_test123456789","status":"paid",
                "order":{"code":"ORDER-25"},"amount":2990,
                "paid_amount":2990,"paid_at":when,
                "currency":"BRL","payment_method":"credit_card",
                "refunded_amount":0,"last_transaction":{
                    "status":"captured","success":True,"amount":2990,
                    "refunded_amount":0}}
        self.assertIsNotNone(validate_paid_charge(
            charge=data,charge_id="ch_test123456789",
            order_reference="ORDER-25",total_cents=2990))
        for changed in (
            {"status":"pending"},
            {"order":{"code":"NOT-OUR-ORDER"}},
            {"paid_amount":2900},
            {"paid_at":None},
            {"refunded_amount":1},
            {"status":"chargedback"},
            {"last_transaction":{"status":"authorized_pending_capture",
                                  "success":True,"amount":2990,"refunded_amount":0}},
            {"currency":"USD"},
        ):
            with self.subTest(changed=changed), self.assertRaises(PaymentProviderError):
                validate_paid_charge(
                    charge={**data,**changed},charge_id="ch_test123456789",
                    order_reference="ORDER-25",total_cents=2990)


@override_settings(FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED=True)
class ProofRecordingTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.operator=User.objects.create_user(username="pr26-cash-operator")
        self.stranger=User.objects.create_user(username="pr26-stranger")
        self.tenant=Tenant.objects.create(
            name="QA caixa e-commerce",slug="qa-payment-pr26",platform="nuvemshop",
            external_store_id="12345",status=Tenant.Status.ACTIVE,
            loyalty_live_enabled=True,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,user=self.operator,role=TenantMembership.Role.OWNER,
        )
        self.sale=SaleRecord.objects.create(
            tenant=self.tenant,channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="ORDER-25",reported_total_cents=2990,
            eligible_amount_cents=0,order_status=SaleRecord.OrderStatus.PAID,
        )
        self.paid_at=timezone.now()-timedelta(minutes=1)
        self.secret="sk_test_"+"x"*32
        self.charge={"id":"ch_test123456789","status":"paid",
                     "order":{"code":"ORDER-25"},"amount":2990,
                     "paid_amount":2990,"paid_at":self.paid_at.isoformat(),
                     "currency":"BRL","payment_method":"credit_card",
                     "refunded_amount":0,"last_transaction":{
                         "status":"captured","success":True,"amount":2990,
                         "refunded_amount":0}}

    def test_signed_in_independent_get_creates_immutable_evidence_once(self):
        opener=FakeOpener(self.charge)
        with patch.dict(os.environ,{
            "FIDELIZA_PAGARME_BOUND_TENANT_ID":str(self.tenant.pk),
            "FIDELIZA_PAGARME_SECRET_KEY":self.secret,
        }):
            evidence,created=confirm_pagarme_charge(
                sale_id=self.sale.pk,charge_id=self.charge["id"],opener=opener)
            again,repeated=confirm_pagarme_charge(
                sale_id=self.sale.pk,charge_id=self.charge["id"],opener=opener)
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(evidence.pk,again.pk)
        self.assertEqual(VerifiedPaymentProof.objects.count(),1)
        self.assertEqual(FinancialEvidence.objects.count(),1)
        self.assertEqual(opener.last.get_method(),"GET")
        self.assertEqual(opener.last.full_url,
            "https://api.pagar.me/core/v5/charges/ch_test123456789")
        self.assertTrue(opener.last.get_header("Authorization").startswith("Basic "))
        self.assertEqual(evidence.provider,"pagarme_v5")
        self.assertEqual(evidence.verification_digest.__len__(),64)
        with self.assertRaises(ValueError):
            evidence.save()
        self.assertEqual(self.sale.eligible_amount_cents,0)

    def test_different_store_or_wrong_order_never_creates_proof(self):
        other=Tenant.objects.create(
            name="QA outsider",slug="qa-other-pr26",
            status=Tenant.Status.ACTIVE,loyalty_live_enabled=True,
        )
        sale=SaleRecord.objects.create(
            tenant=other,channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="ORDER-25",reported_total_cents=2990,
            eligible_amount_cents=0,order_status=SaleRecord.OrderStatus.PAID,
        )
        with patch.dict(os.environ,{
            "FIDELIZA_PAGARME_BOUND_TENANT_ID":str(self.tenant.pk),
            "FIDELIZA_PAGARME_SECRET_KEY":self.secret,
        }):
            with self.assertRaises(PaymentProofBlocked):
                confirm_pagarme_charge(
                    sale_id=sale.pk,charge_id=self.charge["id"],
                    opener=FakeOpener(self.charge))
            bad={**self.charge,"order":{"code":"CHANGED"}}
            with self.assertRaises(PaymentProofBlocked):
                confirm_pagarme_charge(
                    sale_id=self.sale.pk,charge_id=self.charge["id"],
                    opener=FakeOpener(bad))
        self.assertFalse(FinancialEvidence.objects.exists())

    def test_cash_close_requires_operator_membership_is_immutable_and_idempotent(self):
        sale=SaleRecord.objects.create(
            tenant=self.tenant,channel=SaleRecord.Channel.COUNTER,
            external_reference="COUNTER-25",reported_total_cents=2990,
            eligible_amount_cents=2990,order_status=SaleRecord.OrderStatus.PAID,
        )
        with self.assertRaises(PaymentProofBlocked):
            attest_cash_close(
                sale_id=sale.pk,operator=self.stranger,
                external_receipt="CLOSE-0001",closed_at=self.paid_at)
        proof,created=attest_cash_close(
            sale_id=sale.pk,operator=self.operator,
            external_receipt="CLOSE-0001",closed_at=self.paid_at)
        repeat,is_new=attest_cash_close(
            sale_id=sale.pk,operator=self.operator,
            external_receipt="CLOSE-0001",closed_at=self.paid_at)
        self.assertTrue(created)
        self.assertFalse(is_new)
        self.assertEqual(proof.pk,repeat.pk)
        self.assertEqual(VerifiedPaymentProof.objects.get().operator,self.operator)
        with self.assertRaises(ValueError):
            CashClosing.objects.get().delete()

    def test_postgres_immutable_psp_proof_blocks_direct_update_delete(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only trigger test")
        with patch.dict(os.environ,{
            "FIDELIZA_PAGARME_BOUND_TENANT_ID":str(self.tenant.pk),
            "FIDELIZA_PAGARME_SECRET_KEY":self.secret,
        }):
            evidence,_=confirm_pagarme_charge(
                sale_id=self.sale.pk,charge_id=self.charge["id"],
                opener=FakeOpener(self.charge))
        proof=VerifiedPaymentProof.objects.get(evidence=evidence)
        sale=SaleRecord.objects.create(
            tenant=self.tenant,channel=SaleRecord.Channel.COUNTER,
            external_reference="COUNTER-PG-26",reported_total_cents=2990,
            eligible_amount_cents=2990,order_status=SaleRecord.OrderStatus.PAID,
        )
        attest_cash_close(
            sale_id=sale.pk,operator=self.operator,
            external_receipt="CLOSE-PG-26",closed_at=self.paid_at)
        closing=CashClosing.objects.get()
        for table,ident in (
            ("loyalty_financialevidence",evidence.pk),
            ("loyalty_verifiedpaymentproof",proof.pk),
            ("loyalty_cashclosing",closing.pk),
        ):
            for statement in ("UPDATE "+table+" SET id=id WHERE id=%s",
                              "DELETE FROM "+table+" WHERE id=%s"):
                with self.subTest(table=table,sql=statement), self.assertRaises(DatabaseError):
                    with transaction.atomic():
                        with connection.cursor() as cur:
                            cur.execute(statement,[ident])

    def test_payment_proof_disabled_by_default_in_runtime(self):
        with override_settings(FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED=False):
            with self.assertRaises(PaymentProofBlocked):
                attest_cash_close(
                    sale_id=self.sale.pk,operator=self.operator,
                    external_receipt="CLOSE-0002",closed_at=self.paid_at)


class CommercialReleaseFailClosedTests(TestCase):
    def test_commercial_cannot_enable_without_real_postgres_and_financial_gates(self):
        user=get_user_model().objects.create_superuser(
            username="pr26-super",email="qa@example.invalid",password="synthetic",
        )
        tenant=Tenant.objects.create(
            name="QA commercial candidate",slug="commercial-pr26",
            platform="nuvemshop",external_store_id="12345",
            status=Tenant.Status.ACTIVE,
        )
        with patch.dict(os.environ,{
            "FIDELIZA_ENVIRONMENT":"production",
            "FIDELIZA_COMMERCIAL_GO_LIVE_APPROVED":"YES_RELEASE_REVIEWED",
            "FIDELIZA_COMMERCIAL_ALLOWED_TENANT_ID":str(tenant.pk),
            "FIDELIZA_DEPLOYED_SHA":"a"*40,
        }):
            with self.assertRaises(CommandError):
                call_command("set_loyalty_release",
                    mode="commercial",tenant_id=str(tenant.pk),
                    actor_id=str(user.pk),ticket="GO-LIVE-PR26",
                    approved_sha="a"*40,enable=True,
                    confirm="ENABLE_COMMERCIAL")
        tenant.refresh_from_db()
        self.assertFalse(tenant.loyalty_live_enabled)
