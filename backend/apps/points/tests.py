"""Motor de pontos: dados sintéticos, sem HTTP, sem autorização financeira."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackWallet, CashbackEvent
from .models import PointEntry, PointEvent, PointLot, PointWallet
from .services import (
    create_pending_lot, transition_points,
    lot_balances, wallet_balances,
)


class PointLedgerTest(TestCase):
    def setUp(self):
        self.tenant=Tenant.objects.create(
            name="Pontos QA",slug="pontos-qa",
            status=Tenant.Status.ACTIVE,platform="independent",
        )
        self.other=Tenant.objects.create(
            name="Outra Loja QA",slug="outra-pontos-qa",
            status=Tenant.Status.ACTIVE,platform="independent",
        )
        now=timezone.now()
        self.participant=ProgramParticipant.objects.create(
            tenant=self.tenant,display_name="Membro QA",
            contact_email="test@example.invalid",
            consent_at=now-timedelta(seconds=10),terms_version="v1",
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            status=ProgramParticipant.Status.ACTIVE,
        )
        self.other_member=ProgramParticipant.objects.create(
            tenant=self.other,display_name="Outro membro",
            contact_email="test@example.invalid",
            consent_at=now-timedelta(seconds=10),terms_version="v1",
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            status=ProgramParticipant.Status.ACTIVE,
        )
        self.paid_at=timezone.now()
        self.release_at=self.paid_at+timedelta(days=7)
        self.expire_at=self.paid_at+timedelta(days=190)
        self.args={
            "participant":self.participant,
            "channel":"nuvemshop",
            "source_reference":"pedido-9485",
            "eligible_amount_cents":12000,
            "points":120,
            "rule_version":"rule-1",
            "paid_at":self.paid_at,
            "unlock_at":self.release_at,
            "expires_at":self.expire_at,
            "verification_digest":"a"*64,
        }

    def issue(self, **updates):
        return create_pending_lot(**{**self.args,**updates})

    def movement(self, lot, kind, amount, key, **extra):
        return transition_points(
            lot_id=lot.id,kind=kind,amount=amount,
            idempotency_key=key,**extra,
        )

    def test_hard_block_in_production_even_if_env_is_set(self):
        with self.assertRaises(PermissionError):
            self.issue()
        self.assertFalse(PointWallet.objects.exists())
        self.assertFalse(PointEntry.objects.exists())

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_credit_once_same_order_even_if_rule_changes(self):
        lot,created=self.issue()
        self.assertTrue(created)
        self.assertEqual(lot_balances(lot),{
            "pending":120,"available":0,"reserved":0,
        })
        same,created=self.issue()
        self.assertFalse(created)
        self.assertEqual(same.id,lot.id)
        self.assertEqual(PointLot.objects.count(),1)
        self.assertEqual(PointEvent.objects.count(),1)
        self.assertEqual(wallet_balances(lot.wallet),lot_balances(lot))
        for updates in [
            {"points":125},
            {"rule_version":"rule-2"},
            {"participant":self.other_member},
        ]:
            with self.subTest(updates=updates),self.assertRaises(ValueError):
                self.issue(**updates)
        self.assertEqual(PointWallet.objects.count(),1)
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_release_after_hold_partial_refund_expiry(self):
        lot,_=self.issue()
        with self.assertRaises(ValueError):
            self.movement(lot,PointEvent.Kind.RELEASE,120,"release-one")
        with patch("apps.points.services.timezone.now",
                   return_value=self.release_at+timedelta(seconds=1)):
            evt,created=self.movement(lot,PointEvent.Kind.RELEASE,120,"release-one")
            self.assertTrue(created)
            self.assertEqual(evt.kind,PointEvent.Kind.RELEASE)
            self.assertEqual(lot_balances(lot),{
                "pending":0,"available":120,"reserved":0,
            })
            same,created=self.movement(lot,PointEvent.Kind.RELEASE,120,"release-one")
            self.assertFalse(created)
            self.assertEqual(evt.id,same.id)
            self.movement(lot,PointEvent.Kind.REVERSE_AVAILABLE,20,"refund-partial")
            self.assertEqual(lot_balances(lot)["available"],100)
            with self.assertRaises(ValueError):
                self.movement(lot,PointEvent.Kind.REVERSE_AVAILABLE,110,"overrefund")
            with self.assertRaises(ValueError):
                self.movement(lot,PointEvent.Kind.EXPIRE_AVAILABLE,100,"expire-early")
        with patch("apps.points.services.timezone.now",
                   return_value=self.expire_at+timedelta(seconds=1)):
            self.movement(lot,PointEvent.Kind.EXPIRE_AVAILABLE,100,"expire-rest")
            self.assertEqual(lot_balances(lot),{
                "pending":0,"available":0,"reserved":0,
            })
            with self.assertRaises(ValueError):
                self.movement(lot,PointEvent.Kind.RELEASE,1,"late-release")

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_reversal_before_release_and_invalid_replay(self):
        lot,_=self.issue()
        self.movement(lot,PointEvent.Kind.REVERSE_PENDING,50,"partial-refund")
        self.assertEqual(lot_balances(lot)["pending"],70)
        with self.assertRaises(ValueError):
            self.movement(lot,PointEvent.Kind.REVERSE_PENDING,51,"partial-refund")
        with self.assertRaises(ValueError):
            self.movement(lot,PointEvent.Kind.REVERSE_PENDING,71,"too-many")
        with patch("apps.points.services.timezone.now",
                   return_value=self.release_at+timedelta(seconds=1)):
            self.movement(lot,PointEvent.Kind.RELEASE,70,"released-remainder")
        self.assertEqual(lot_balances(lot)["available"],70)

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_points_held_during_reservation_and_proof_on_redeem(self):
        lot,_=self.issue()
        with patch("apps.points.services.timezone.now",
                   return_value=self.release_at+timedelta(seconds=1)):
            self.movement(lot,PointEvent.Kind.RELEASE,120,"release")
            self.movement(lot,PointEvent.Kind.RESERVE,100,"reserve-1")
            self.assertEqual(lot_balances(lot),{
                "pending":0,"available":20,"reserved":100,
            })
            with self.assertRaises(ValueError):
                self.movement(lot,PointEvent.Kind.RESERVE,21,"second-reservation")
            with self.assertRaises(ValueError):
                self.movement(lot,PointEvent.Kind.REDEEM,100,"redeem-no-proof")
            self.movement(lot,PointEvent.Kind.CANCEL_RESERVE,30,"cancel-part")
            self.assertEqual(lot_balances(lot)["available"],50)
            self.movement(lot,PointEvent.Kind.REDEEM,70,"redeem-1",
                          external_receipt="checkout-confirmed-synthetic")
            self.assertEqual(lot_balances(lot),{
                "pending":0,"available":50,"reserved":0,
            })
            self.assertEqual(sum(lot_balances(lot).values()),50)

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_lots_are_immutable_and_wrong_data_is_rejected(self):
        lot,_=self.issue()
        lot.points_issued=1000
        with self.assertRaises(ValueError):
            lot.save()
        with self.assertRaises(ValueError):
            lot.delete()
        event=PointEvent.objects.get(lot=lot)
        event.amount=999
        with self.assertRaises(ValueError):
            event.save()
        entry=PointEntry.objects.get(event=event)
        with self.assertRaises(ValueError):
            entry.delete()
        self.assertEqual(PointLot.objects.get(pk=lot.pk).points_issued,120)
        for updates in [
            {"source_reference":" "}, {"points":True}, {"points":0},
            {"eligible_amount_cents":-1}, {"verification_digest":"unsafe"},
            {"expires_at":self.release_at},
            {"unlock_at":self.paid_at-timedelta(seconds=1)},
            {"paid_at":self.paid_at-timedelta(days=10)},
        ]:
            with self.subTest(updates=updates),self.assertRaises(ValueError):
                self.issue(source_reference="different-"+str(len(str(updates))),
                           **{k:v for k,v in updates.items() if k!="source_reference"},
                           **({"source_reference":updates["source_reference"]}
                               if "source_reference" in updates else {}))
        self.assertEqual(PointLot.objects.count(),1)

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_two_tenants_with_same_reference_keep_separate_wallets(self):
        a,_=self.issue()
        b,_=self.issue(participant=self.other_member)
        self.assertNotEqual(a.id,b.id)
        self.assertNotEqual(a.wallet_id,b.wallet_id)
        self.assertEqual(PointLot.objects.count(),2)
        self.assertEqual(wallet_balances(a.wallet)["pending"],120)
        self.assertEqual(wallet_balances(b.wallet)["pending"],120)

    @override_settings(FIDELIZA_POINTS_WRITES_ENABLED=True)
    def test_suspended_member_cannot_get_new_lot_or_release(self):
        lot,_=self.issue()
        self.participant.status=ProgramParticipant.Status.PAUSED
        self.participant.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            self.issue(source_reference="pedido-9486")
        with patch("apps.points.services.timezone.now",
                   return_value=self.release_at+timedelta(seconds=1)):
            with self.assertRaises(ValueError):
                self.movement(lot,PointEvent.Kind.RELEASE,120,"release-blocked")
        self.assertEqual(lot_balances(lot)["pending"],120)
