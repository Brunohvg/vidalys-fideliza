"""Adesão automática após prova de e-mail e correspondência única na Nuvemshop.

Roda somente no container API, que tem as credenciais OAuth; nunca
repassa token de acesso ou PII ao Redis/worker. Falhas preservam o estado
email_verified, para revisão manual sem criar benefícios.
"""
from django.conf import settings
from django.db import DatabaseError

from apps.nuvemshop.customer_lookup import (
    CustomerReadError, exact_email_match, read_customer_candidates,
)
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.scopes import has_customer_access
from apps.nuvemshop.security import OAuthConfigurationError, config, decrypt_token
from apps.tenants.models import Tenant

from .customer_link_service import CustomerLinkConflict, link_verified_submission
from .email_proof import digest
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission


def auto_link_after_verified_email(token: str) -> str:
    """'linked' ou 'pending_review'; sem consultar rede quando não habilitado.

    Chamada APENAS depois de consume_challenge(token,'verify') retornar
    sucesso, nunca por token não verificado ou por solicitação de retirada.
    """
    if not (settings.FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
            and settings.FIDELIZA_EMAIL_DELIVERY_ENABLED):
        return "pending_review"
    challenge=EnrollmentEmailChallenge.objects.select_related(
        "submission__tenant"
    ).filter(token_digest=digest(token),
             purpose=EnrollmentEmailChallenge.Purpose.VERIFY,
             consumed_at__isnull=False).first()
    if not challenge:
        return "pending_review"
    submission=challenge.submission
    tenant=submission.tenant
    if (tenant.status!=Tenant.Status.ACTIVE or tenant.platform!="nuvemshop"
            or submission.status!=EnrollmentSubmission.Status.EMAIL_VERIFIED
            or submission.email_verified_at is None
            or submission.withdrawn_at is not None
            or not tenant.external_store_id):
        return "pending_review"
    installed=NuvemshopInstallation.objects.filter(tenant=tenant).first()
    if (not installed or installed.store_id!=tenant.external_store_id
            or not has_customer_access(installed.scope,
                                       customer_preview_enabled=True)):
        return "pending_review"
    try:
        cfg=config()
        if cfg.client_id!=installed.client_id:
            return "pending_review"
        access_token=decrypt_token(installed.token_ciphertext,cfg.token_keys)
        customers=read_customer_candidates(
            store_id=int(installed.store_id),access_token=access_token,
            user_agent=cfg.user_agent,email=submission.email,
        )
        status,customer_id=exact_email_match(customers,submission.email)
        if status!="one_exact_match" or not customer_id:
            return "pending_review"
        _,created=link_verified_submission(
            tenant_id=tenant.id,submission_id=submission.id,
            customer_id=customer_id,client_id=cfg.client_id,
            store_id=installed.store_id,actor=None,
            source="nuvemshop_customer_auto_verified_email",
        )
    except (CustomerReadError, OAuthConfigurationError, ValueError,
            CustomerLinkConflict, EnrollmentSubmission.DoesNotExist,
            Tenant.DoesNotExist, DatabaseError):
        return "pending_review"
    return "linked" if created else "pending_review"
