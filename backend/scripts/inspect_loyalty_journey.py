"""Pré-voo read-only da jornada de uma loja na homologação.

Exemplo: python scripts/inspect_loyalty_journey.py --slug loja-piloto

Nunca mostra nomes/e-mails de clientes, IDs de pedidos, saldos, tokens,
credenciais ou dados de outras lojas. Não ativa nenhuma funcionalidade.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
import django
django.setup()

from django.conf import settings
from apps.campaigns.models import CampaignDraft
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.privacy_models import PrivacyWebhookRequest
from apps.participants.enrollment_models import (
    EnrollmentSubmission,ProgramTerms,EnrollmentCustomerLink,
)
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackWallet


def inspect(slug:str)->dict:
    tenant=Tenant.objects.get(slug=slug)
    installed=NuvemshopInstallation.objects.filter(tenant=tenant).first()
    connected=bool(
        tenant.status==Tenant.Status.ACTIVE
        and tenant.platform=="nuvemshop"
        and installed is not None
        and tenant.external_store_id
        and str(installed.store_id)==str(tenant.external_store_id)
    )
    terms=ProgramTerms.objects.filter(tenant=tenant,active=True).exists()
    optin=EnrollmentSubmission.objects.filter(
        tenant=tenant,email_verified_at__isnull=False,
    ).exclude(status=EnrollmentSubmission.Status.WITHDRAWN).count()
    members=ProgramParticipant.objects.filter(
        tenant=tenant,status=ProgramParticipant.Status.ACTIVE,
    ).count()
    return {
        "tenant_slug":tenant.slug,
        "tenant_active":tenant.status==Tenant.Status.ACTIVE,
        "nuvemshop_connected":connected,
        "program_terms_approved":terms,
        "public_signup_enabled":bool(settings.FIDELIZA_PUBLIC_SIGNUP_ENABLED),
        "email_delivery_flag_enabled":bool(settings.FIDELIZA_EMAIL_DELIVERY_ENABLED),
        "customer_preview_enabled":bool(
            settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
        ),
        "customer_approval_enabled":bool(
            settings.FIDELIZA_PARTICIPANT_APPROVAL_ENABLED
        ),
        "verified_requests_count":optin,
        "linked_customers_count":EnrollmentCustomerLink.objects.filter(
            tenant=tenant,
        ).count(),
        "active_participants_count":members,
        "campaign_drafts_count":CampaignDraft.objects.filter(tenant=tenant).count(),
        "wallet_records_count":CashbackWallet.objects.filter(tenant=tenant).count(),
        "privacy_requests_open":PrivacyWebhookRequest.objects.filter(
            tenant=tenant,
        ).exclude(state=PrivacyWebhookRequest.State.COMPLETED).count(),
        "paid_order_verification_available":False,
        "live_cashback_granting_available":False,
        "live_redemption_available":False,
        "note":(
            "O relatório usa contagens internas. Flags de e-mail ativas "
            "não provam que SMTP/entrega esteja funcionando. "
            "Pedido pago e cashback real permanecem indisponíveis."
        ),
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug",required=True,help="slug da loja de HOMOLOGAÇÃO")
    args=parser.parse_args()
    try:
        result=inspect(args.slug)
    except Tenant.DoesNotExist:
        print("Loja de homologação não encontrada.",file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
