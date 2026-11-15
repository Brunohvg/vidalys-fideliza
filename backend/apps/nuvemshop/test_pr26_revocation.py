"""PR26: DELETE Nuvemshop em duas fases, uso zero e crédito só após confirmação."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from apps.points.models import PointEntry, PointEvent
from apps.points.services import lot_balances
from apps.nuvemshop.models import NuvemshopCouponIntent
from apps.nuvemshop.coupon_revocation import revoke_coupon, CouponRevokeBlocked
from apps.nuvemshop.coupon_client import get_coupon_by_id, delete_coupon_once, CouponRemoteError
from apps.nuvemshop.test_pr25_pilot import CouponIdempotencyTests
from apps.loyalty.models import LoyaltyVoucher


@override_settings(
    FIDELIZA_NUVEMSHOP_COUPON_REVOCATION_ENABLED=True,
    FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"psp_test"}),
)
class RevocationTests(TestCase):
    setUp=CouponIdempotencyTests.setUp

    def prepared(self):
        with (
            patch("apps.nuvemshop.coupon_service.config", return_value=self.cfg),
            patch("apps.nuvemshop.coupon_service.create_coupon_once", return_value="876"),
        ):
            from apps.nuvemshop.coupon_service import provision_coupon
            provision_coupon(voucher_id=self.voucher.pk,issued_code=self.code)
        return NuvemshopCouponIntent.objects.get(voucher=self.voucher)

    def remote(self):
        return {"id":876,"code":self.code,"used":0,"valid":True,
                "deleted_at":None}

    def test_expired_unused_coupon_deletes_once_and_refunds_reserved_origin(self):
        intent=self.prepared()
        lot=self.voucher.point_allocations.get().lot
        # Estado financeiro sintético de um resgate corretamente reservado.
        for i,(kind,entries) in enumerate((
            (PointEvent.Kind.ACCRUE, [("pending",10)]),
            (PointEvent.Kind.RELEASE,[("pending",-10),("available",10)]),
            (PointEvent.Kind.RESERVE,[("available",-10),("reserved",10)]),
        )):
            event=PointEvent.objects.create(
                lot=lot,kind=kind,amount=10,idempotency_key=f"test26:{i}",
            )
            for bucket,delta in entries:
                PointEntry.objects.create(event=event,bucket=bucket,delta=delta)
        self.voucher.expires_at=timezone.now()-timedelta(minutes=40)
        self.voucher.save(update_fields=["expires_at"])
        with (
            patch("apps.nuvemshop.coupon_revocation.config",return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.get_coupon_by_id",
                  side_effect=[self.remote(),None]) as reads,
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once",
                  return_value=True) as delete,
        ):
            result,released=revoke_coupon(
                intent_id=intent.pk,reason="expired",
            )
            self.assertTrue(released)
            self.assertEqual(result.state,intent.State.REVOKED)
            self.assertEqual(reads.call_count,2)
            delete.assert_called_once()
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.CANCELLED)
        self.assertEqual(lot_balances(lot)["available"],10)
        self.assertEqual(lot_balances(lot)["reserved"],0)
        again,changed=revoke_coupon(intent_id=intent.pk,reason="expired")
        self.assertEqual(again.state,intent.State.REVOKED)
        self.assertFalse(changed)

    def test_remote_used_one_blocks_delete_and_refund(self):
        intent=self.prepared()
        self.voucher.expires_at=timezone.now()-timedelta(minutes=40)
        self.voucher.save(update_fields=["expires_at"])
        with (
            patch("apps.nuvemshop.coupon_revocation.config",return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.get_coupon_by_id",
                  return_value={**self.remote(),"used":1}),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once") as deleted,
        ):
            with self.assertRaises(CouponRevokeBlocked):
                revoke_coupon(intent_id=intent.pk,reason="expired")
            deleted.assert_not_called()
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.RESERVED)
        intent.refresh_from_db()
        self.assertEqual(intent.state,intent.State.REVOKE_UNKNOWN)

    def test_unknown_delete_keeps_reservation(self):
        intent=self.prepared()
        self.voucher.expires_at=timezone.now()-timedelta(minutes=40)
        self.voucher.save(update_fields=["expires_at"])
        with (
            patch("apps.nuvemshop.coupon_revocation.config",return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.get_coupon_by_id",
                  return_value=self.remote()),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once",
                  side_effect=CouponRemoteError("timeout")),
        ):
            with self.assertRaises(CouponRevokeBlocked):
                revoke_coupon(intent_id=intent.pk,reason="expired")
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.RESERVED)
        intent.refresh_from_db()
        self.assertEqual(intent.state,intent.State.REVOKE_UNKNOWN)

    def test_cancelled_order_with_no_psp_capture_cannot_invent_refund(self):
        intent=self.prepared()
        # Mesmo cancelamento na plataforma não prova ausência de captura PSP.
        from apps.sales.models import SaleRecord
        SaleRecord.objects.create(
            tenant=self.tenant,channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="9876",eligible_amount_cents=0,
            reported_total_cents=2000,
            order_status=SaleRecord.OrderStatus.CANCELLED,
        )
        intent.order_id="9876"
        intent.save(update_fields=["order_id"])
        with (
            patch("apps.nuvemshop.coupon_revocation.config",return_value=self.cfg),
            patch("apps.nuvemshop.coupon_revocation.get_coupon_by_id",
                  side_effect=[self.remote(),None]),
            patch("apps.nuvemshop.coupon_revocation.delete_coupon_once",
                  return_value=True),
        ):
            result,released=revoke_coupon(
                intent_id=intent.pk,reason="order_cancelled",
            )
        self.assertEqual(result.state,intent.State.REVOKED)
        self.assertFalse(released)
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state,LoyaltyVoucher.State.RESERVED)
