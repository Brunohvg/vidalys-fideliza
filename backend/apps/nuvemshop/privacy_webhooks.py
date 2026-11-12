"""Webhooks obrigatórios de privacidade da Nuvemshop (LGPD).

HMAC-SHA256 do body bruto com client_secret, nunca token da loja.
Persistência idempotente sem salvar payload pessoal. Protocolo confirmado
somente após transação; concluir exclusão/relatório é etapa distinta.
"""
import hashlib
import hmac
import json
import logging
import os
import re

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from apps.participants.enrollment_models import (
    EnrollmentCustomerLink, EnrollmentEmailChallenge, EnrollmentSubmission,
)
from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation, OAuthAttempt
from .privacy_models import PrivacyWebhookRequest
from .privacy_security import email_identity_digest, privacy_event_key, legacy_event_key, pseudonymous_customer_id


MAX_WEBHOOK_BYTES = 65536
TOPICS = {
    "customer-redact": PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
    "customers-data-request": PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST,
    "store-redact": PrivacyWebhookRequest.Topic.STORE_REDACT,
}
logger=logging.getLogger(__name__)


def _queue_store_sanitization(receipt_id: str):
    try:
        from .tasks import sanitize_store_after_redact
        sanitize_store_after_redact.delay(receipt_id)
    except Exception:
        # O protocolo segue persistido. O comando interno reenvia a fila.
        logger.warning("A fila de limpeza de loja está indisponível; revisão pendente")


HMAC_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")


def _positive_id(value):
    if isinstance(value, bool):
        return None
    if not isinstance(value, (str, int)):
        return None
    raw = str(value)
    if (not raw or len(raw) > 18 or not raw.isascii()
            or not raw.isdecimal() or int(raw) <= 0):
        return None
    return str(int(raw))


def _check_hmac(body, header):
    secret = os.getenv("NUVEMSHOP_CLIENT_SECRET", "").strip()
    client_id = _positive_id(os.getenv("NUVEMSHOP_CLIENT_ID", ""))
    if not secret or not client_id:
        return None  # Falta configuração; devolver 503 para retry do provedor.
    if not isinstance(header, str) or not HMAC_PATTERN.fullmatch(header):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.lower())


def _decode(body, topic):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or (payload.get("event") not in (None, topic)):
        return None
    store_id = _positive_id(payload.get("store_id"))
    if store_id is None:
        return None
    customer_id, request_id = "", ""
    if topic in (
        PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
        PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST,
    ):
        customer = payload.get("customer")
        if not isinstance(customer, dict):
            return None
        customer_id = _positive_id(customer.get("id"))
        if customer_id is None:
            return None
        if topic == PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST:
            request = payload.get("data_request")
            if not isinstance(request, dict):
                return None
            request_id = _positive_id(request.get("id"))
            if request_id is None:
                return None
    # Campos sensíveis do body jamais retornam ao chamador ou ao banco.
    return store_id, customer_id, request_id, payload


def _limited_response(status=202):
    response = JsonResponse({"received": True}, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _revoke_customer(tenant, customer_id, payload):
    """Interromper participação e mensagens de imediato, sem apagar ledger.

    A retenção residual e a eliminação final exigem revisão separada.
    """
    now = timezone.now()
    links = list(EnrollmentCustomerLink.objects.filter(
        tenant=tenant, external_customer_id=customer_id,
    ).values_list("submission_id", "participant_id"))
    submission_ids = [submission_id for submission_id, _ in links]
    participant_ids = [participant_id for _, participant_id in links]
    # Participantes legados podem não ter EnrollmentCustomerLink.
    participant_ids.extend(ProgramParticipant.objects.filter(
        tenant=tenant, external_customer_id=customer_id,
    ).values_list("id", flat=True))
    # O evento da plataforma também pode identificar adesões ainda não
    # vinculadas. O e-mail é lido em memória, nunca salvo no protocolo.
    raw_email = payload.get("customer", {}).get("email")
    candidates = EnrollmentSubmission.objects.filter(tenant=tenant)
    if (isinstance(raw_email, str) and 3 <= len(raw_email) <= 254
            and "@" in raw_email and not any(ord(c) < 32 for c in raw_email)):
        emails = list(candidates.filter(
            email__iexact=raw_email.strip()
        ).values_list("pk", flat=True))
        submission_ids.extend(emails)
    challenge_count = submission_count = participant_count = link_count = 0
    if submission_ids:
        ids = set(submission_ids)
        challenge_count = EnrollmentEmailChallenge.objects.filter(
            submission_id__in=ids, consumed_at__isnull=True,
        ).update(consumed_at=now)
        submission_count = EnrollmentSubmission.objects.filter(
            tenant=tenant, pk__in=ids,
        ).update(
            name="", email="", marketing_opt_in=False,
            status=EnrollmentSubmission.Status.WITHDRAWN,
            withdrawn_at=now,
        )
    if participant_ids:
        pseudonym=pseudonymous_customer_id(
            str(tenant.external_store_id), customer_id,
            os.environ["NUVEMSHOP_CLIENT_SECRET"].strip(),
        )
        participant_count = ProgramParticipant.objects.filter(
            tenant=tenant, pk__in=set(participant_ids)
        ).update(
            external_customer_id=pseudonym,
            display_name="", contact_email="",
            status=ProgramParticipant.Status.WITHDRAWN,
            last_program_activity_at=None,
        )
        link_count = EnrollmentCustomerLink.objects.filter(
            tenant=tenant, external_customer_id=customer_id,
        ).update(external_customer_id=pseudonym)
    return {
        "email_challenges_disabled": int(challenge_count),
        "enrollment_submissions_sanitized": int(submission_count),
        "participants_sanitized": int(participant_count),
        "customer_links_pseudonymized": int(link_count),
        "unlinked_submissions_identifiable_by_email": bool(
            isinstance(raw_email, str) and "@" in raw_email
        ),
        "retention_review_required": True,
        "backup_review_required": True,
    }
    # Mesmo depois de desativar contato/adesão, há IDs em links e eventual
    # histórico contábil; não alegar exclusão total antes da revisão.


def _revoke_store(tenant):
    """Desinstalação/solicitação da loja: cortar acesso e segredos antes da revisão."""
    if tenant.status != Tenant.Status.SUSPENDED:
        tenant.status = Tenant.Status.SUSPENDED
        tenant.save(update_fields=["status", "updated_at"])
    # Dados de loja continuam preservados apenas para revisão da eliminação.
    NuvemshopInstallation.objects.filter(tenant=tenant).delete()
    OAuthAttempt.objects.filter(tenant=tenant).delete()
    TenantMembership.objects.filter(tenant=tenant).delete()


@csrf_exempt
@require_POST
@never_cache
def privacy_webhook(request, kind):
    """Rotas por tema (payload LGPD pode não incluir o campo event)."""
    topic = TOPICS.get(kind)
    if topic is None:
        return HttpResponse(status=404)
    if request.content_type != "application/json":
        return HttpResponse(status=415)
    length = request.META.get("CONTENT_LENGTH", "")
    if length:
        try:
            if int(length) > MAX_WEBHOOK_BYTES:
                return HttpResponse(status=413)
        except ValueError:
            return HttpResponse(status=400)
    body = request.body
    if len(body) > MAX_WEBHOOK_BYTES:
        return HttpResponse(status=413)
    result = _check_hmac(body, request.headers.get("X-Linkedstore-Hmac-Sha256", ""))
    if result is None:
        return HttpResponse(status=503)
    if not result:
        return HttpResponse(status=401)
    decoded = _decode(body, topic)
    if decoded is None:
        return HttpResponse(status=400)
    store_id, customer_id, request_id, payload = decoded
    secret = os.environ["NUVEMSHOP_CLIENT_SECRET"].strip()
    key = privacy_event_key(topic, store_id, customer_id, request_id, secret)
    old_key = legacy_event_key(topic, store_id, customer_id, request_id)
    email_hash = email_identity_digest(payload.get("customer", {}).get("email")
                                      if isinstance(payload.get("customer"), dict)
                                      else None, secret)
    client_id = _positive_id(os.getenv("NUVEMSHOP_CLIENT_ID", ""))
    try:
        with transaction.atomic():
            tenant = Tenant.objects.select_for_update().filter(
                platform="nuvemshop", external_store_id=store_id,
            ).first()
            if tenant is not None:
                install = NuvemshopInstallation.objects.filter(tenant=tenant).first()
                if install is not None and install.client_id != client_id:
                    tenant = None  # Nunca acessar credenciais de outro app.
            existing = PrivacyWebhookRequest.objects.select_for_update().filter(
                event_key__in=(key, old_key)
            ).first()
            # Se a loja não estava mapeada na primeira entrega, processar o
            # reenvio depois de identificá-la. Não perder o direito do titular.
            if existing is not None and not (
                tenant is not None
                and existing.state == PrivacyWebhookRequest.State.UNKNOWN_STORE
            ):
                if (topic == PrivacyWebhookRequest.Topic.STORE_REDACT
                        and existing.tenant_id
                        and existing.sanitized_at is None
                        and existing.state == PrivacyWebhookRequest.State.NEEDS_REVIEW):
                    transaction.on_commit(
                        lambda rid=str(existing.pk): _queue_store_sanitization(rid)
                    )
                return _limited_response()
            state = (PrivacyWebhookRequest.State.NEEDS_REVIEW
                     if tenant is not None else PrivacyWebhookRequest.State.UNKNOWN_STORE)
            if existing is None:
                receipt = PrivacyWebhookRequest.objects.create(
                    tenant=tenant, store_id=store_id, topic=topic, event_key=key,
                    customer_id=customer_id, request_id=request_id,
                    customer_email_digest=email_hash,
                    state=state if topic != PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
                          else (PrivacyWebhookRequest.State.PENDING if tenant is not None
                                else PrivacyWebhookRequest.State.UNKNOWN_STORE),
                    reason_code=("pending_erasure" if topic != PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
                                 else "report_not_delivered") if tenant is not None else "unmapped_store",
                )
            else:
                existing.tenant=tenant
                existing.state=(PrivacyWebhookRequest.State.PENDING
                    if topic == PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
                    else PrivacyWebhookRequest.State.NEEDS_REVIEW)
                existing.reason_code=("report_not_delivered"
                    if topic == PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST
                    else "pending_erasure")
                if email_hash:
                    existing.customer_email_digest = email_hash
                existing.save(update_fields=[
                    "tenant", "state", "reason_code", "customer_email_digest"
                ])
                receipt = existing
            if tenant is not None and topic == PrivacyWebhookRequest.Topic.CUSTOMER_REDACT:
                summary = _revoke_customer(tenant, customer_id, payload)
                receipt.sanitized_at = timezone.now()
                receipt.sanitization_summary = summary
                receipt.save(update_fields=["sanitized_at","sanitization_summary"])
            elif tenant is not None and topic == PrivacyWebhookRequest.Topic.STORE_REDACT:
                # Suspender contas e revogar OAuth imediatamente. O trabalho
                # volumoso de limpeza de dados é executado no worker.
                _revoke_store(tenant)
                transaction.on_commit(
                    lambda rid=str(receipt.pk): _queue_store_sanitization(rid)
                )
            # Nunca marcar COMPLETED aqui: 202 comprova apenas aceitação.
            # Sem publicação externa, e-mail ou escrita na API Nuvemshop.
        return _limited_response()
    except Exception:
        # Transação falhou; não devolver 2xx para que a plataforma reenvie.
        # Não logar body nem mensagem de erro potencialmente sensível.
        return HttpResponse(status=503)
