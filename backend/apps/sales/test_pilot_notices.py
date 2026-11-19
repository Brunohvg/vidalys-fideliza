"""Avisos do piloto: libera carência vencida, avisa uma única vez e só com consentimento."""
import hashlib
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import EmailDispatch
from apps.participants.enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms
from apps.participants.models import ProgramParticipant
from apps.points.models import PointLot
from apps.points.services import create_pending_lot, lot_balances
from apps.tenants.models import Tenant
from .models import CounterPilot, CreditNotice, PointRuleDraft, ProgramMode
from .notices import scan_all, scan_tenant
from .tasks import notice_copy


class PilotNoticeTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="notice-owner")
        self.tenant = Tenant.objects.create(name="Bibelô QA", slug="notice-qa", platform="independent",
                                            status=Tenant.Status.ACTIVE)
        PointRuleDraft.objects.create(tenant=self.tenant, points=3, per_cents=100, hold_days=0,
                                      validity_days=90, updated_by=self.owner)
        CounterPilot.objects.create(tenant=self.tenant, active=True, updated_by=self.owner)
        self.ana = self.member("Ana", opt_in=True)
        self.bia = self.member("Bia", opt_in=False)
        self.settings = override_settings(FIDELIZA_ENVIRONMENT="homolog",
                                          FIDELIZA_PILOT_TENANTS=frozenset({str(self.tenant.id)}))
        self.settings.enable()
        self.addCleanup(self.settings.disable)

    def member(self, name, *, opt_in):
        now = timezone.now()
        participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name=name, contact_email=f"{name.lower()}@example.invalid",
            external_customer_id=None, consent_at=now - timedelta(days=60),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL, terms_version="v1",
            status=ProgramParticipant.Status.ACTIVE,
        )
        ProgramParticipant.objects.filter(pk=participant.pk).update(joined_at=now - timedelta(days=60))
        participant.refresh_from_db()
        terms, _ = ProgramTerms.objects.get_or_create(
            tenant=self.tenant, version="v1",
            defaults={"title": "Regulamento", "body": "Regras do clube para o teste. " * 3,
                      "privacy_notice": "Dados protegidos neste teste do clube. " * 4, "approved_at": now})
        invite = EnrollmentInvite.objects.create(tenant=self.tenant, terms=terms, token_digest=hashlib.sha256(name.encode()).hexdigest(),
                                                 expires_at=now + timedelta(hours=1), consumed_at=now)
        EnrollmentSubmission.objects.create(
            tenant=self.tenant, invitation=invite, terms=terms, name=name, email=f"{name.lower()}@example.invalid",
            accepted_at=now, terms_digest="c" * 64, marketing_opt_in=opt_in, email_verified_at=now, participant=participant,
        )
        return participant

    def lot(self, participant, *, unlock_days, expire_days, ref):
        now = timezone.now()
        lot, _created = create_pending_lot(
            participant=participant, channel="counter", source_reference=f"counter:{ref}", eligible_amount_cents=10000,
            points=300, rule_version="pilot-v1", paid_at=now - timedelta(days=30),
            unlock_at=now + timedelta(days=unlock_days), expires_at=now + timedelta(days=expire_days),
            verification_digest="a" * 64,
        )
        return lot

    def test_release_then_notify_once_and_only_with_consent(self):
        ana_lot = self.lot(self.ana, unlock_days=-1, expire_days=60, ref="ana-1")
        bia_lot = self.lot(self.bia, unlock_days=-1, expire_days=60, ref="bia-1")
        self.lot(self.ana, unlock_days=3, expire_days=60, ref="ana-future")
        with mock.patch("apps.core.delivery_tracking.transaction.on_commit", lambda fn: None):
            first = scan_tenant(self.tenant)
            again = scan_tenant(self.tenant)
        self.assertEqual(lot_balances(ana_lot)["available"], 300)        # liberado sem ninguém abrir o clube
        self.assertEqual(lot_balances(bia_lot)["available"], 300)
        self.assertEqual(first["released"], 1)                            # só Ana aceitou novidades
        self.assertEqual(again["released"], 0)                            # nunca repete
        self.assertEqual(CreditNotice.objects.filter(kind="released").count(), 2)
        self.assertFalse(CreditNotice.objects.get(lot=bia_lot).emailed)
        self.assertEqual(EmailDispatch.objects.filter(kind="notice").count(), 1)

    def test_expiring_window_and_pilot_off(self):
        soon = self.lot(self.ana, unlock_days=-20, expire_days=4, ref="ana-soon")
        self.lot(self.ana, unlock_days=-20, expire_days=30, ref="ana-later")
        with mock.patch("apps.core.delivery_tracking.transaction.on_commit", lambda fn: None):
            result = scan_tenant(self.tenant)
        self.assertEqual(result["expiring"], 1)
        self.assertEqual(result["released"], 0)                          # liberações antigas não são avisadas
        self.assertEqual(list(CreditNotice.objects.filter(kind="expiring").values_list("lot_id", flat=True)), [soon.pk])
        CounterPilot.objects.filter(tenant=self.tenant).update(active=False)
        self.assertEqual(scan_all(), {})

    def test_copy_in_money_for_giftback_and_points_otherwise(self):
        when = datetime(2026, 12, 20)
        subject, title, text, label = notice_copy(store="Bibelô", gift=True, kind="released", amount=1577,
                                                  expires_at=when, min_order_cents=8000)
        self.assertIn("R$ 15,77", subject)
        self.assertIn("a partir de R$ 80,00", text)
        self.assertEqual(label, "Ver meu crédito")
        subject, *_ = notice_copy(store="Bibelô", gift=False, kind="expiring", amount=1200, expires_at=when)
        self.assertIn("1.200 pontos", subject)
        self.assertTrue(ProgramMode)  # importado: modo giftback usa o mesmo ledger
        self.assertTrue(PointLot)
