"""Minimização de dados próprios após desinstalação da loja.

Corta os dados de contato/marketing, mantém apenas vínculos mínimos e
registros sujeitos a revisão de retenção. A rotina é idempotente, roda no
worker e NUNCA marca o pedido LGPD como totalmente concluído.

Importante: não depende do client_secret Nuvemshop. Ele fica restrito
ao container API; o worker usa a chave interna Django para os
pseudônimos que não precisam ser reidentificados.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.campaigns.models import CampaignDraft
from apps.customers.models import CustomerProfile, ChannelCustomerReference, VerifiedCustomerContact
from apps.costs.models import CostItem
from apps.participants.enrollment_models import (
    EnrollmentCustomerLink,
    EnrollmentEmailChallenge,
    EnrollmentSubmission, EnrollmentInvite, MemberAccessChallenge,
)
from apps.participants.models import ProgramParticipant
from apps.tenants.branding_models import TenantBranding, TenantBrandingAudit
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEvent

from .models import NuvemshopInstallation
from .privacy_models import PrivacyWebhookRequest
from .privacy_security import pseudonymous_customer_id


def sanitize_store_privacy(receipt_id: str) -> str:
    """Retorna estado seguro sem IDs de cliente ou informações pessoais."""
    with transaction.atomic():
        receipt = PrivacyWebhookRequest.objects.select_for_update().filter(
            pk=receipt_id,
            topic=PrivacyWebhookRequest.Topic.STORE_REDACT,
        ).first()
        if receipt is None or receipt.tenant_id is None:
            return "unmapped"
        if receipt.sanitized_at is not None:
            return "already_sanitized"
        tenant = Tenant.objects.select_for_update().get(pk=receipt.tenant_id)
        # Não apagar a loja enquanto sua integração ainda estiver em uso.
        if tenant.status != Tenant.Status.SUSPENDED:
            return "store_still_active"
        if NuvemshopInstallation.objects.filter(tenant=tenant).exists():
            return "connection_still_active"

        now = timezone.now()
        pending_challenges = EnrollmentEmailChallenge.objects.filter(
            submission__tenant=tenant, consumed_at__isnull=True,
        ).update(consumed_at=now)
        # Invalidate all outstanding public invitation/access tokens as well.
        pending_invites = EnrollmentInvite.objects.filter(
            tenant=tenant, consumed_at__isnull=True,
        ).update(consumed_at=now)
        pending_access = MemberAccessChallenge.objects.filter(
            submission__tenant=tenant, consumed_at__isnull=True,
        ).update(consumed_at=now)
        submissions = EnrollmentSubmission.objects.filter(tenant=tenant).update(
            name="", email="", marketing_opt_in=False,
            status=EnrollmentSubmission.Status.WITHDRAWN,
            withdrawn_at=now,
        )

        # Iteração em lotes; sem carga total do catálogo de clientes na memória.
        participants_changed = 0
        links_changed = 0
        batch = []
        link_batch = []
        for participant in ProgramParticipant.objects.filter(
            tenant=tenant,
        ).iterator(chunk_size=200):
            old_ref = participant.external_customer_id
            if old_ref and old_ref.startswith("anon:"):
                new_ref = old_ref
            else:
                # Standalone members may have NULL external customer IDs.
                # Use the internal UUID to keep pseudonyms distinct.
                source = old_ref or ("local:" + str(participant.pk))
                new_ref = pseudonymous_customer_id(
                    receipt.store_id, source, settings.SECRET_KEY,
                )
            participant.external_customer_id = new_ref
            participant.display_name = ""
            participant.contact_email = ""
            participant.status = ProgramParticipant.Status.WITHDRAWN
            participant.last_program_activity_at = None
            batch.append(participant)
            participants_changed += 1
            if len(batch) >= 200:
                ProgramParticipant.objects.bulk_update(
                    batch, ["external_customer_id","display_name",
                            "contact_email","status","last_program_activity_at"],
                    batch_size=200,
                )
                batch.clear()
        if batch:
            ProgramParticipant.objects.bulk_update(
                batch, ["external_customer_id","display_name",
                        "contact_email","status","last_program_activity_at"],
                batch_size=200,
            )

        # Atualizar referências de Customer em vínculos que conservamos
        # apenas para trilha do consentimento. A chave de ligação é UUID
        # interno, não o identificador pessoal da Nuvemshop.
        for link in EnrollmentCustomerLink.objects.filter(
            tenant=tenant,
        ).select_related("participant").iterator(chunk_size=200):
            link.external_customer_id=link.participant.external_customer_id
            link_batch.append(link)
            links_changed += 1
            if len(link_batch)>=200:
                EnrollmentCustomerLink.objects.bulk_update(
                    link_batch, ["external_customer_id"],batch_size=200,
                )
                link_batch.clear()
        if link_batch:
            EnrollmentCustomerLink.objects.bulk_update(
                link_batch, ["external_customer_id"],batch_size=200,
            )

        # Verified contact digests, names, birth dates and channel IDs are
        # not needed to retain the immutable financial ledger after uninstall.
        # Preserve CustomerProfile UUID/FKs, but remove identifying fields.
        verified_contacts, _ = VerifiedCustomerContact.objects.filter(
            tenant=tenant,
        ).delete()
        channel_references, _ = ChannelCustomerReference.objects.filter(
            tenant=tenant,
        ).delete()
        profiles_scrubbed = CustomerProfile.objects.filter(tenant=tenant).update(
            display_name="", birth_date=None, birth_date_consent_at=None,
            birth_date_verified_at=None,
        )

        # Configurações comerciais próprias do aplicativo podem ser
        # eliminadas após desligar a loja; não são escrituração fiscal.
        branding_audits, _ = TenantBrandingAudit.objects.filter(
            tenant=tenant
        ).delete()
        branding, _ = TenantBranding.objects.filter(tenant=tenant).delete()
        cost_rows, _ = CostItem.objects.filter(tenant=tenant).delete()
        draft_rows, _ = CampaignDraft.objects.filter(tenant=tenant).delete()

        retained_events = CashbackEvent.objects.filter(
            wallet__tenant=tenant,
        ).count()
        # NÃO apagar ledger, termos de consentimento, histórico de
        # protocolos, IDs de pedidos antigos nem backups sem revisão.
        receipt.sanitized_at = now
        receipt.reason_code = "retention_review_required"
        receipt.sanitization_summary = {
            "email_challenges_disabled": int(pending_challenges),
            "invites_disabled": int(pending_invites),
            "member_access_disabled": int(pending_access),
            "verified_contacts_deleted": int(verified_contacts),
            "channel_references_deleted": int(channel_references),
            "customer_profiles_scrubbed": int(profiles_scrubbed),
            "enrollment_submissions_sanitized": int(submissions),
            "participants_sanitized": int(participants_changed),
            "customer_links_pseudonymized": int(links_changed),
            "branding_audit_rows_removed": int(branding_audits),
            "branding_rows_removed": int(branding),
            "cost_rows_removed": int(cost_rows),
            "campaign_drafts_removed": int(draft_rows),
            "ledger_events_retained": int(retained_events),
            "manual_retention_review_required": True,
            "backup_review_required": True,
        }
        receipt.save(update_fields=[
            "sanitized_at","sanitization_summary","reason_code",
        ])
        return "sanitized_pending_review"
