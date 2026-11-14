"""Identidade omnichannel sem loja conectada e sem creditar saldo."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant
from apps.points.models import PointWallet
from apps.wallets.models import CashbackWallet

from .models import ChannelCustomerReference, CustomerProfile, VerifiedCustomerContact
from .services import (
    IdentityConflict, attach_channel_reference, attach_verified_contact,
    find_verified_customer, normalize_email, normalize_phone,
)


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=False,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class OmnichannelIdentityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Clube WhatsApp", slug="clube-whatsapp", status=Tenant.Status.ACTIVE,
        )
        self.other = Tenant.objects.create(
            name="Outra Loja", slug="outra-loja-identidade", status=Tenant.Status.ACTIVE,
        )
        self.member = self.make_member(self.tenant, "cliente@example.com")

    def make_member(self, tenant, email):
        return ProgramParticipant.objects.create(
            tenant=tenant, display_name="Cliente Teste", contact_email=email,
            consent_at=timezone.now() - timedelta(minutes=5),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )

    def test_standalone_email_identity_is_idempotent_without_wallets(self):
        profile, created = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            email=" CLIENTE@EXAMPLE.COM ", proof_method="email_otp",
        )
        again, duplicate = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            email="cliente@example.com", proof_method="email_otp",
        )
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(profile.pk, again.pk)
        self.assertEqual(find_verified_customer(
            tenant_id=self.tenant.pk, email="cliente@example.com"
        ).pk, profile.pk)
        self.assertEqual(VerifiedCustomerContact.objects.count(), 1)
        self.assertFalse(PointWallet.objects.exists())
        self.assertFalse(CashbackWallet.objects.exists())

    def test_whatsapp_and_store_customer_share_profile_and_participant(self):
        profile, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            email=self.member.contact_email, proof_method="email_otp",
        )
        phone_profile, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            phone_e164="+5531999999999", proof_method="whatsapp_otp",
        )
        self.assertEqual(profile.pk, phone_profile.pk)
        reference, created = attach_channel_reference(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            channel="nuvemshop", external_id="3521",
        )
        again, new = attach_channel_reference(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            channel="nuvemshop", external_id="3521",
        )
        self.assertTrue(created)
        self.assertFalse(new)
        self.assertEqual(reference.pk, again.pk)
        attach_channel_reference(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            channel="vidalys_flow", external_id="flow-100",
        )
        self.assertEqual(find_verified_customer(
            tenant_id=self.tenant.pk, phone_e164="+5531999999999"
        ).pk, profile.pk)
        self.assertEqual(CustomerProfile.objects.count(), 1)
        self.assertEqual(ChannelCustomerReference.objects.count(), 2)

    def test_same_email_in_different_tenants_never_shares_profile(self):
        other_member = self.make_member(self.other, self.member.contact_email)
        first, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            email=self.member.contact_email, proof_method="email_otp",
        )
        second, _ = attach_verified_contact(
            tenant_id=self.other.pk, participant_id=other_member.pk,
            email=other_member.contact_email, proof_method="email_otp",
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.tenant_id, second.tenant_id)

    def test_duplicate_verified_contact_cannot_merge_wallets(self):
        second = self.make_member(self.tenant, "CLIENTE@example.com")
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            email=self.member.contact_email, proof_method="email_otp",
        )
        with self.assertRaises(IdentityConflict):
            attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=second.pk,
                email=second.contact_email, proof_method="email_otp",
            )
        self.assertEqual(CustomerProfile.objects.count(), 1)

    def test_unverified_or_badly_formatted_contact_is_rejected(self):
        with self.assertRaises(ValueError):
            attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.member.pk,
                email=self.member.contact_email, proof_method="self_reported",
            )
        with self.assertRaises(ValueError):
            attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.member.pk,
                phone_e164="31999999999", proof_method="whatsapp_otp",
            )
        with self.assertRaises(IdentityConflict):
            attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.member.pk,
                email="outra@example.com", proof_method="email_otp",
            )
        self.assertEqual(normalize_email(" TEST@EXAMPLE.COM "), "test@example.com")
        self.assertEqual(normalize_phone("+5531999999999"), "+5531999999999")
        self.assertFalse(CustomerProfile.objects.exists())

    def test_secret_rotation_fallback_keeps_existing_identity(self):
        with override_settings(SECRET_KEY="first-test-key", SECRET_KEY_FALLBACKS=[]):
            first, created = attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.member.pk,
                email=self.member.contact_email, proof_method="email_otp",
            )
        self.assertTrue(created)
        with override_settings(
            SECRET_KEY="second-test-key", SECRET_KEY_FALLBACKS=["first-test-key"],
        ):
            found = find_verified_customer(
                tenant_id=self.tenant.pk, email=self.member.contact_email,
            )
            same, duplicated = attach_verified_contact(
                tenant_id=self.tenant.pk, participant_id=self.member.pk,
                email=self.member.contact_email, proof_method="email_otp",
            )
        self.assertEqual(first.pk, found.pk)
        self.assertEqual(first.pk, same.pk)
        self.assertFalse(duplicated)
        self.assertEqual(VerifiedCustomerContact.objects.count(), 1)

    def test_channel_external_reference_is_never_reassigned(self):
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            email=self.member.contact_email, proof_method="email_otp",
        )
        other_member = self.make_member(self.tenant, "outro@example.com")
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=other_member.pk,
            email=other_member.contact_email, proof_method="email_otp",
        )
        attach_channel_reference(
            tenant_id=self.tenant.pk, participant_id=self.member.pk,
            channel="nuvemshop", external_id="782",
        )
        with self.assertRaises(IdentityConflict):
            attach_channel_reference(
                tenant_id=self.tenant.pk, participant_id=other_member.pk,
                channel="nuvemshop", external_id="782",
            )
        self.assertEqual(ChannelCustomerReference.objects.count(), 1)
