"""PR26: PSP read-back, caixa com dupla conferência, CPF e gates comerciais."""
import os
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import connection, DatabaseError, transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from apps.customers.services import attach_verified_contact, normalize_cpf
from apps.loyalty.models import FinancialEvidence, PaymentProofAudit
from apps.loyalty.payment_proof import (
    PaymentProofBlocked, validate_pagarme_capture,
    record_cash_dual_control, record_pagarme_capture,
)
from apps.nuvemshop.order_recheck_service import _buyer_identity
from apps.participants.models import ProgramParticipant
from apps.sales.models import SaleRecord, SaleEventReceipt
from apps.tenants.models import Tenant, TenantMembership


class CpfChecks(SimpleTestCase):
    def test_cpf_check_digits_are_real_and_not_accepted_by_guess(self):
        self.assertEqual(normalize_cpf("529.982.247-25"), "52998224725")
        for bad in ("111.111.111-11", "529.982.247-24", "abc", "", None, "1114447773X"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_cpf(bad)


class ProofTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.op=User.objects.create_user(username="pr26-operator")
        self.reviewer=User.objects.create_user(username="pr26-reviewer")
        self.tenant=Tenant.objects.create(name="QA loja caixa", slug="qa-payment-proof",
            status=Tenant.Status.ACTIVE, loyalty_live_enabled=True)
        for user in (self.op,self.reviewer):
            TenantMembership.objects.create(tenant=self.tenant, user=user,
                role=TenantMembership.Role.OWNER)
        self.sale=SaleRecord.objects.create(
            tenant=self.tenant, channel=SaleRecord.Channel.COUNTER,
            external_reference="POS-2026-1234", eligible_amount_cents=2500,
            reported_total_cents=2500, order_status=SaleRecord.OrderStatus.PAID,
            submitted_by=self.op,
        )
        self.charge_id="ch_ABCDEF12345678"
        self.order_id="or_ABCDEF12345678"

    def charge(self, *, sale=None, **changes):
        sale=sale or self.sale
        payload=dict(
            id=self.charge_id, status="paid", amount=sale.reported_total_cents,
            paid_amount=sale.reported_total_cents, refunded_amount=0,
            currency="BRL", payment_method="credit_card",
            paid_at=timezone.now().isoformat(),
            order={"id":self.order_id, "code":sale.external_reference},
            last_transaction=dict(
                status="captured", success=True,
                amount=sale.reported_total_cents, refunded_amount=0,
            ),
        )
        payload.update(changes)
        return payload

    @override_settings(
        FIDELIZA_PAYMENT_PROOF_ENABLED=True,
        FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"pagarme_v5"}),
    )
    def test_psp_capture_validates_remote_and_unique_proof(self):
        evidence, created=record_pagarme_capture(
            sale_id=self.sale.pk, charge_id=self.charge_id,
            remote=self.charge(), secret_verified=True,
        )
        self.assertTrue(created)
        self.assertEqual(evidence.amount_cents,2500)
        self.assertEqual(evidence.provider,"pagarme_v5")
        self.assertEqual(PaymentProofAudit.objects.get().evidence_id,evidence.pk)
        repeat,created=record_pagarme_capture(
            sale_id=self.sale.pk, charge_id=self.charge_id,
            remote=self.charge(), secret_verified=True,
        )
        self.assertFalse(created)
        self.assertEqual(repeat.pk,evidence.pk)

    def test_charge_auth_only_partial_refund_and_other_order_all_rejected(self):
        for changes in (
            {"status":"pending"}, {"status":"chargedback"},
            {"amount":2400}, {"paid_amount":2400}, {"refunded_amount":100},
            {"last_transaction":{"status":"authorized_pending_capture",
                                 "success":True,"amount":2500,"refunded_amount":0}},
            {"last_transaction":{"status":"captured","success":True,
                                 "amount":2500,"refunded_amount":1}},
            {"order":{"id":self.order_id,"code":"ORDER-OTHER"}},
        ):
            with self.subTest(changes=changes), self.assertRaises(PaymentProofBlocked):
                validate_pagarme_capture(
                    charge=self.charge(**changes), sale=self.sale,
                    charge_id=self.charge_id,
                )
        self.assertFalse(FinancialEvidence.objects.exists())

    @override_settings(
        FIDELIZA_CASH_DUAL_CONTROL_ENABLED=True,
        FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"cash_dual_control"}),
    )
    def test_cash_needs_two_tenant_operators_and_exact_amount(self):
        now=timezone.now()
        with self.assertRaises(PaymentProofBlocked):
            record_cash_dual_control(
                sale_id=self.sale.pk, receipt_reference="CASH-001",
                operator_id=self.op.pk, reviewer_id=self.op.pk,
                received_at=now, counted_cents=2500,
            )
        with self.assertRaises(PaymentProofBlocked):
            record_cash_dual_control(
                sale_id=self.sale.pk, receipt_reference="CASH-001",
                operator_id=self.op.pk, reviewer_id=self.reviewer.pk,
                received_at=now, counted_cents=2499,
            )
        evidence,new=record_cash_dual_control(
            sale_id=self.sale.pk, receipt_reference="CASH-001",
            operator_id=self.op.pk, reviewer_id=self.reviewer.pk,
            received_at=now, counted_cents=2500,
        )
        self.assertTrue(new)
        audit=PaymentProofAudit.objects.get(evidence=evidence)
        self.assertEqual(audit.operator_id,self.op.pk)
        self.assertEqual(audit.reviewer_id,self.reviewer.pk)
        self.assertEqual(evidence.provider,"cash_dual_control")

    @override_settings(
        FIDELIZA_CASH_DUAL_CONTROL_ENABLED=True,
        FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"cash_dual_control"}),
    )
    def test_flow_sale_requires_authenticated_ingestion_receipt_plus_dual_cash_check(self):
        flow = SaleRecord.objects.create(
            tenant=self.tenant, channel=SaleRecord.Channel.VIDALYS_FLOW,
            external_reference="FLOW-ORDER-26",
            source_order_key="a" * 64, eligible_amount_cents=0,
            reported_total_cents=2500, order_status=SaleRecord.OrderStatus.PAID,
        )
        now=timezone.now()
        args=dict(
            sale_id=flow.pk, receipt_reference="FLOW-CASH-REC-26",
            operator_id=self.op.pk, reviewer_id=self.reviewer.pk,
            received_at=now, counted_cents=2500,
        )
        with self.assertRaises(PaymentProofBlocked):
            record_cash_dual_control(**args)
        SaleEventReceipt.objects.create(
            tenant=self.tenant, sale=flow,
            channel=SaleRecord.Channel.VIDALYS_FLOW,
            source_event_id="signed-flow-26",
            idempotency_key="d" * 64, payload_digest="e" * 64,
            reported_status=SaleRecord.OrderStatus.PAID,
            reported_total_cents=2500,
            outcome=SaleEventReceipt.Outcome.APPLIED,
        )
        evidence, fresh=record_cash_dual_control(**args)
        self.assertTrue(fresh)
        self.assertEqual(evidence.sale_id, flow.pk)
        self.assertEqual(evidence.provider, "cash_dual_control")

    @override_settings(
        FIDELIZA_PAYMENT_PROOF_ENABLED=True,
        FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"pagarme_v5"}),
    )
    def test_postgres_sql_update_delete_cannot_mutate_payment_proof(self):
        if connection.vendor!="postgresql":
            self.skipTest("Triggers somente no PostgreSQL")
        evidence,_=record_pagarme_capture(
            sale_id=self.sale.pk, charge_id=self.charge_id,
            remote=self.charge(), secret_verified=True,
        )
        audit=PaymentProofAudit.objects.get(evidence=evidence)
        for model,pk in ((PaymentProofAudit,audit.pk),
                         (FinancialEvidence,evidence.pk)):
            with self.subTest(table=model._meta.db_table):
                with self.assertRaises(DatabaseError),transaction.atomic():
                    model.objects.filter(pk=pk).update(verified_at=timezone.now())
                with self.assertRaises(DatabaseError),transaction.atomic():
                    model.objects.filter(pk=pk).delete()
        self.assertTrue(PaymentProofAudit.objects.filter(pk=audit.pk).exists())

    def test_checkout_contact_fraud_rejected_even_when_email_matches(self):
        participant=ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="QA buyer",
            contact_email="buyer@example.invalid", consent_at=timezone.now(),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1",
        )
        profile,_=attach_verified_contact(
            tenant_id=self.tenant.pk,participant_id=participant.pk,
            email=participant.contact_email,proof_method="email_otp",
        )
        self.assertIsNone(_buyer_identity({
            "contact_email":participant.contact_email,
            "contact_identification":"11144477735",
        },self.tenant)[1])
        self.assertIsNone(_buyer_identity({
            "contact_email":participant.contact_email,
            "contact_phone":"+5531988888888",
        },self.tenant)[1])
        attach_verified_contact(
            tenant_id=self.tenant.pk,participant_id=participant.pk,
            cpf="52998224725",proof_method="provider_confirmed",
        )
        _,same=_buyer_identity({
            "contact_email":participant.contact_email,
            "contact_identification":"529.982.247-25",
        },self.tenant)
        self.assertEqual(same.pk,profile.pk)

    def test_commercial_mode_fails_closed_without_checkout_enforcement(self):
        superuser=get_user_model().objects.create_superuser(
            username="pr26-admin",email="ops@example.invalid",password="x",
        )
        with patch.dict(os.environ,{
            "FIDELIZA_ENVIRONMENT":"production",
            "FIDELIZA_COMMERCIAL_ACTIVATION_APPROVAL":"YES_COMMERCIAL_APPROVED",
            "FIDELIZA_DEPLOYED_SHA":"a"*40,
        }):
            with self.assertRaises(CommandError):
                call_command("set_loyalty_pilot",tenant_id=str(self.tenant.pk),
                    actor_id=str(superuser.pk),ticket="COMMERCIAL-QA-26",
                    approved_sha="a"*40,enable=True,mode="commercial",
                    confirm="ENABLE_COMMERCIAL")
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.loyalty_live_enabled)  # already QA, not changed
