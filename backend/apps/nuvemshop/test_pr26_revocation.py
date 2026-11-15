"""PR26 external coupon DELETE/refund and checkout identity, all synthetic."""
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.db import connection, DatabaseError, transaction
from django.utils import timezone

from apps.points.models import PointEntry, PointEvent
from apps.points.services import lot_balances
from apps.loyalty.models import LoyaltyVoucher
from apps.nuvemshop.coupon_revocation import revoke_and_release, RevocationBlocked
from apps.nuvemshop.models import (
    NuvemshopCouponIntent, NuvemshopCouponRevocationAudit,
)
from apps.nuvemshop.test_pr25_pilot import CouponIdempotencyTests
from apps.nuvemshop.order_recheck_service import _paid_coupon_from_order, RecheckBlocked
from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
from apps.sales.models import SaleRecord
from apps.customers.services import attach_verified_contact


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"psp_test"}),
    FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED=True,
)
class RevocationAndOwnershipTests(CouponIdempotencyTests):
    """Reuses PR25 isolated member/voucher + OAuth installation fixtures."""

    def _credit_reservation(self):
        lot=self.voucher.point_allocations.get().lot
        for kind, deltas in (
            (PointEvent.Kind.ACCRUE,{"pending":10}),
            (PointEvent.Kind.RELEASE,{"pending":-10,"available":10}),
            (PointEvent.Kind.RESERVE,{"available":-10,"reserved":10}),
        ):
            ev=PointEvent.objects.create(
                lot=lot,kind=kind,amount=10,
                idempotency_key="pr26:"+kind+":"+str(lot.pk),
            )
            for bucket,delta in deltas.items():
                PointEntry.objects.create(event=ev,bucket=bucket,delta=delta)
        return lot

    def _issued_coupon(self):
        with (
            patch("apps.nuvemshop.coupon_service.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_service.create_coupon_once", return_value="876"),
        ):
            from apps.nuvemshop.coupon_service import provision_coupon
            return provision_coupon(voucher_id=self.voucher.pk, issued_code=self.code)[0]

    def test_expired_coupon_deleted_verified_then_refunds_only_its_points(self):
        lot=self._credit_reservation()
        intent=self._issued_coupon()
        self.assertEqual(lot_balances(lot)["reserved"],10)
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        self.voucher.refresh_from_db()
        remote={"id":876,"code":self.code,"valid":True,"deleted_at":None,"used":0}
        deleted={"id":876,"code":self.code,"valid":False,
                 "deleted_at":timezone.now().isoformat(),"used":0}
        with (
            patch("apps.nuvemshop.coupon_revocation.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id",
                  side_effect=[remote,deleted]) as got,
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once",
                  return_value=True) as deleted_call,
        ):
            result,changed=revoke_and_release(intent_id=intent.pk,reason="expired")
        self.assertTrue(changed)
        self.assertEqual(result.state,NuvemshopCouponIntent.State.REVOKED)
        self.assertEqual(self.voucher.point_allocations.count(),1)
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.CANCELLED)
        self.assertEqual(lot_balances(lot)["reserved"],0)
        self.assertEqual(lot_balances(lot)["available"],10)
        deleted_call.assert_called_once()
        self.assertEqual(got.call_count,2)
        self.assertEqual(NuvemshopCouponRevocationAudit.objects.count(),1)
        again,once=revoke_and_release(intent_id=intent.pk,reason="expired")
        self.assertFalse(once)

    def test_expired_invalid_but_unused_coupon_must_be_deleted_before_refund(self):
        lot = self._credit_reservation()
        intent = self._issued_coupon()
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        invalid = {"id":876,"code":self.code,"valid":False,
                   "deleted_at":None,"used":0}
        removed = {"id":876,"code":self.code,"valid":False,
                   "deleted_at":timezone.now().isoformat(),"used":0}
        with (
            patch("apps.nuvemshop.coupon_revocation.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id",
                  side_effect=[invalid, removed]) as fetch,
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once",
                  return_value=True) as delete,
        ):
            _, changed = revoke_and_release(intent_id=intent.pk, reason="expired")
        self.assertTrue(changed)
        self.assertEqual(fetch.call_count, 2)
        delete.assert_called_once()
        self.assertEqual(lot_balances(lot)["reserved"], 0)
        self.assertEqual(lot_balances(lot)["available"], 10)
        self.assertEqual(NuvemshopCouponRevocationAudit.objects.count(), 1)
        intent.refresh_from_db()
        self.assertIsNotNone(intent.verified_unused_at)
        _, repeated = revoke_and_release(intent_id=intent.pk, reason="expired")
        self.assertFalse(repeated)
        self.assertEqual(lot_balances(lot)["available"], 10)

    def test_stale_unused_snapshot_and_remote_404_do_not_refund(self):
        lot = self._credit_reservation()
        intent = self._issued_coupon()
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        intent.verified_unused_at = timezone.now()-timedelta(minutes=10)
        intent.save(update_fields=["verified_unused_at"])
        with (
            patch("apps.nuvemshop.coupon_revocation.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id", return_value=None),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once") as remover,
            self.assertRaises(RevocationBlocked),
        ):
            revoke_and_release(intent_id=intent.pk, reason="expired")
        remover.assert_not_called()
        self.assertEqual(lot_balances(lot)["reserved"], 10)

    def test_preexisting_revoking_intent_does_not_repeat_external_delete(self):
        intent = self._issued_coupon()
        NuvemshopCouponIntent.objects.filter(pk=intent.pk).update(
            state=NuvemshopCouponIntent.State.REVOKING)
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        with (
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id") as fetch,
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once") as delete,
            self.assertRaises(RevocationBlocked),
        ):
            revoke_and_release(intent_id=intent.pk, reason="expired")
        fetch.assert_not_called()
        delete.assert_not_called()

    def test_psp_evidence_without_verified_receipt_cannot_settle(self):
        from apps.loyalty.models import FinancialEvidence
        from apps.nuvemshop.coupon_settlement import (
            settle_coupon_after_psp_capture, CouponSettlementBlocked)
        intent = self._issued_coupon()
        NuvemshopCouponIntent.objects.filter(pk=intent.pk).update(
            order_id="9876", state=NuvemshopCouponIntent.State.APPLIED)
        sale = SaleRecord.objects.create(
            tenant=self.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="9876", order_status=SaleRecord.OrderStatus.PAID,
            reported_total_cents=1990, eligible_amount_cents=1990,
        )
        evidence = FinancialEvidence.objects.create(
            tenant=self.tenant, sale=sale, kind=FinancialEvidence.Kind.CAPTURE,
            provider="pagarme_v5", external_event_id="synthetic-fake",
            amount_cents=1990, verification_digest="a"*64,
            occurred_at=timezone.now(), verified_at=timezone.now(),
        )
        with self.assertRaises(CouponSettlementBlocked):
            settle_coupon_after_psp_capture(
                intent_id=intent.pk, capture_evidence_id=evidence.pk)
        intent.refresh_from_db()
        self.assertEqual(intent.state, NuvemshopCouponIntent.State.APPLIED)

    def test_preexisting_remote_404_without_unused_proof_does_not_refund(self):
        lot = self._credit_reservation()
        intent = self._issued_coupon()
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        with (
            patch("apps.nuvemshop.coupon_revocation.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id",
                  return_value=None),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once") as delete,
            self.assertRaises(RevocationBlocked),
        ):
            revoke_and_release(intent_id=intent.pk, reason="expired")
        delete.assert_not_called()
        self.assertEqual(lot_balances(lot)["reserved"], 10)
        self.assertEqual(NuvemshopCouponRevocationAudit.objects.count(), 0)

    def test_unconfirmed_delete_never_refunds_ledger(self):
        lot=self._credit_reservation()
        intent=self._issued_coupon()
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        from apps.nuvemshop.coupon_client import CouponRemoteError
        with (
            patch("apps.nuvemshop.coupon_revocation.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id",
                  side_effect=CouponRemoteError("timeout")),
            self.assertRaises(RevocationBlocked),
        ):
            revoke_and_release(intent_id=intent.pk,reason="expired")
        self.voucher.refresh_from_db()
        intent.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.RESERVED)
        self.assertEqual(intent.state,NuvemshopCouponIntent.State.REVOKING)
        self.assertEqual(lot_balances(lot)["reserved"],10)
        self.assertEqual(NuvemshopCouponRevocationAudit.objects.count(),0)

    def test_used_coupon_cannot_be_refunded_even_if_provider_marks_invalid(self):
        lot=self._credit_reservation()
        intent=self._issued_coupon()
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        self.voucher.refresh_from_db()
        used={"id":876,"code":self.code,"valid":False,
              "deleted_at":None,"used":1}
        with (
            patch("apps.nuvemshop.coupon_revocation.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id",
                  return_value=used),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once") as deletion,
            self.assertRaises(RevocationBlocked),
        ):
            revoke_and_release(intent_id=intent.pk,reason="expired")
        deletion.assert_not_called()
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.RESERVED)
        self.assertEqual(lot_balances(lot)["reserved"],10)

    def test_postgres_revocation_proof_blocks_sql_updates_and_deletes(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only immutable audit")
        self._credit_reservation()
        intent=self._issued_coupon()
        LoyaltyVoucher.objects.filter(pk=self.voucher.pk).update(
            expires_at=timezone.now()-timedelta(minutes=35))
        remote={"id":876,"code":self.code,"valid":True,
                "deleted_at":None,"used":0}
        disabled={"id":876,"code":self.code,"valid":False,
                  "deleted_at":"2026-11-15","used":0}
        with (
            patch("apps.nuvemshop.coupon_revocation.config",return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.inspect_coupon_by_id",
                  side_effect=[remote,disabled]),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once",
                  return_value=True),
        ):
            revoke_and_release(intent_id=intent.pk,reason="expired")
        audit=NuvemshopCouponRevocationAudit.objects.get(intent=intent)
        table="nuvemshop_nuvemshopcouponrevocationaudit"
        for statement in (
            f"UPDATE {table} SET id=id WHERE id=%s",
            f"DELETE FROM {table} WHERE id=%s",
        ):
            with self.subTest(sql=statement), self.assertRaises(DatabaseError):
                with transaction.atomic():
                    with connection.cursor() as cur:
                        cur.execute(statement,[audit.pk])

    def test_preissue_ownership_blocks_anonymous_coupon_until_otp(self):
        from apps.nuvemshop.coupon_service import PilotCouponBlocked
        with override_settings(FIDELIZA_PREISSUE_OWNERSHIP_CHECK_ENABLED=True):
            with self.assertRaises(PilotCouponBlocked):
                self._issued_coupon()
            self.assertFalse(NuvemshopCouponIntent.objects.exists())
            self.participant.contact_email = "pr28-owner@example.invalid"
            self.participant.save(update_fields=["contact_email"])
            attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.participant.pk,
                email=self.participant.contact_email, proof_method="email_otp",
            )
            intent = self._issued_coupon()
            self.assertEqual(intent.state, NuvemshopCouponIntent.State.ISSUED)

    def test_cpf_is_only_stored_as_tenant_hmac_after_provider_proof(self):
        from apps.customers.services import attach_verified_contact, find_verified_customer
        from apps.customers.models import VerifiedCustomerContact
        cpf = "52998224725"  # CPF algorithm fixture, not a real customer record.
        with self.assertRaises(ValueError):
            attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.participant.pk,
                cpf=cpf, proof_method="email_otp",
            )
        profile, created = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            cpf=cpf, proof_method="provider_confirmed",
        )
        self.assertTrue(created)
        self.assertEqual(find_verified_customer(tenant_id=self.tenant.pk, cpf=cpf).pk, profile.pk)
        item = VerifiedCustomerContact.objects.get(kind="cpf")
        self.assertNotIn(cpf, item.lookup_digest)
        self.assertEqual(len(item.lookup_digest), 64)

    def test_foreign_checkout_email_cannot_use_other_member_coupon(self):
        self.participant.contact_email="verified-pr26@example.invalid"
        self.participant.save(update_fields=["contact_email"])
        profile,_=attach_verified_contact(
            tenant_id=self.tenant.pk,participant_id=self.participant.pk,
            email=self.participant.contact_email,proof_method="email_otp",
        )
        intent=self._issued_coupon()
        event=OrderWebhookEvent.objects.create(
            tenant=self.tenant,store_id="54321",order_id="9876",
            topic=OrderWebhookEvent.Topic.PAID,dedupe_key="d"*64,
        )
        sale=SaleRecord.objects.create(
            tenant=self.tenant,channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="9876",order_status=SaleRecord.OrderStatus.PAID,
            reported_total_cents=1990,eligible_amount_cents=0,
            customer_profile=profile,
        )
        remote_order={
            "payment_status":"paid","status":"open",
            "contact_email":self.participant.contact_email,
            # A verified email must NOT cover up an unverified/different one.
            "customer":{"email":"fraudulent@example.invalid"},
            "coupon_id":876,"coupon":[{"id":876,"code":self.code}],
            "discount_coupon":"1.00","total":"19.90",
        }
        with self.assertRaises(RecheckBlocked):
            _paid_coupon_from_order(
                event=event,order=remote_order,sale=sale,profile=profile)
        intent.refresh_from_db()
        self.assertEqual(intent.state,NuvemshopCouponIntent.State.ISSUED)
        self.assertEqual(intent.order_id,"")
