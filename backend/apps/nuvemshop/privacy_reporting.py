"""Relatório de acesso: somente dados próprios do Fideliza de um cliente.

Nunca exporta token OAuth, hash de desafio de e-mail ou informações de outras
lojas. Não consulta a Nuvemshop nem afirma ser relatório de toda a plataforma.
"""
import hashlib
import json
import os

from django.db.models import Q

from apps.participants.enrollment_models import EnrollmentCustomerLink, EnrollmentSubmission
from apps.participants.models import ProgramParticipant
from apps.wallets.models import CashbackEvent

from .privacy_models import PrivacyWebhookRequest
from .privacy_security import email_identity_digest, pseudonymous_customer_id


class PrivacyReportError(RuntimeError):
    pass


def _iso(value):
    return value.isoformat() if value else None


def build_customer_report(receipt: PrivacyWebhookRequest):
    """Build deterministic (JSON bytes, SHA256, completeness) without persistence.

    Receipt identity must be validated by tenant-scoped caller. A missing email
    digest means pending unlinked consents cannot be identified reliably.
    """
    if receipt.topic != PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST:
        raise PrivacyReportError("not_a_data_request")
    if not receipt.tenant_id:
        raise PrivacyReportError("unmapped_store")
    secret=os.getenv("NUVEMSHOP_CLIENT_SECRET","").strip()
    if not secret:
        raise PrivacyReportError("missing_secret")
    pseudonym=pseudonymous_customer_id(receipt.store_id,receipt.customer_id,secret)
    identity=Q(external_customer_id=receipt.customer_id) | Q(
        external_customer_id=pseudonym
    )
    participants=list(
        ProgramParticipant.objects.filter(
            identity, tenant_id=receipt.tenant_id,
        ).order_by("id")
    )
    links=list(
        EnrollmentCustomerLink.objects.filter(
            identity, tenant_id=receipt.tenant_id,
        ).select_related("submission","submission__terms").order_by("id")
    )
    # A aceitação pode ter ocorrido antes do vínculo com a conta Nuvemshop.
    # Buscar pela identidade HMAC recebida no webhook, nunca por nome parcial.
    submission_ids={link.submission_id for link in links}
    if receipt.customer_email_digest:
        for item in EnrollmentSubmission.objects.filter(
            tenant_id=receipt.tenant_id,
        ).only("id","email").iterator(chunk_size=300):
            if email_identity_digest(item.email, secret) == receipt.customer_email_digest:
                submission_ids.add(item.id)
    submissions=list(
        EnrollmentSubmission.objects.filter(
            tenant_id=receipt.tenant_id,
            pk__in=submission_ids,
        ).select_related("terms").order_by("id")
    )
    # Uma exclusão anterior pode ter apagado o e-mail de solicitações
    # que ainda não estavam vinculadas. Não declarar um relatório completo
    # se essa associação deixou de poder ser comprovada.
    has_previous_redaction=PrivacyWebhookRequest.objects.filter(
        tenant_id=receipt.tenant_id,
        store_id=receipt.store_id,
        customer_id=receipt.customer_id,
        topic=PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
    ).exists()
    member_ids=[p.id for p in participants]
    event_count=CashbackEvent.objects.filter(
        wallet__tenant_id=receipt.tenant_id,
        wallet__participant_id__in=member_ids,
    ).count()
    if event_count > 2000 or len(submissions)>1000:
        raise PrivacyReportError("manual_large_report")
    events=CashbackEvent.objects.filter(
        wallet__tenant_id=receipt.tenant_id,
        wallet__participant_id__in=member_ids,
    ).select_related("wallet").prefetch_related("entries").order_by("created_at","id")
    report={
        "documento": "Relatório dos dados armazenados pelo Vidalys Fideliza",
        "versao": 1,
        "solicitacao": receipt.request_id,
        "loja": receipt.store_id,
        "cliente_nuvemshop": receipt.customer_id,
        "escopo": (
            "Somente dados controlados pelo Vidalys Fideliza. "
            "Não inclui todos os dados mantidos pela Nuvemshop nem por outros aplicativos."
        ),
        "cobertura":{
            "cadastros_vinculados":True,
            "aceites_sem_vinculo_identificaveis":bool(receipt.customer_email_digest)
                and not has_previous_redaction,
            "exclusao_anterior_exige_revisao":has_previous_redaction,
            "pedidos_nuvemshop_nao_consultados":True,
        },
        "participacoes":[{
            "id":str(item.id),
            "nome":item.display_name,
            "email":item.contact_email,
            "situacao":item.status,
            "cliente_referencia":item.external_customer_id,
            "aceite_em":_iso(item.consent_at),
            "canal":item.consent_channel,
            "versao_regulamento":item.terms_version,
            "criado_em":_iso(item.joined_at),
        } for item in participants],
        "aceites":[{
            "id":str(item.id),
            "nome":item.name,
            "email":item.email,
            "aceite_em":_iso(item.accepted_at),
            "email_confirmado_em":_iso(item.email_verified_at),
            "retirada_em":_iso(item.withdrawn_at),
            "situacao":item.status,
            "autorizou_marketing":item.marketing_opt_in,
            "versao_regulamento":item.terms.version,
            "titulo_regulamento":item.terms.title,
        } for item in submissions],
        "vinculos":[{
            "participacao":str(item.participant_id),
            "aceite":str(item.submission_id),
            "vinculado_em":_iso(item.confirmed_at),
        } for item in links],
        "movimentos_financeiros_internos":[{
            "participacao":str(item.wallet.participant_id),
            "tipo":item.kind,
            "valor_centavos":item.amount_cents,
            "pedido_referencia":item.source_order_id,
            "versao_regra":item.rule_version,
            "registrado_em":_iso(item.created_at),
            "lancamentos":[{
                "tipo":entry.bucket,
                "variacao_centavos":entry.delta_cents,
            } for entry in item.entries.all()],
        } for item in events],
        "aviso": (
            "Este extrato inclui registros de consentimento e carteira interna. "
            "Um movimento interno não comprova pagamento, saldo resgatável "
            "ou emissão fiscal."
        ),
    }
    data=(json.dumps(report,ensure_ascii=False,sort_keys=True,
                     separators=(",",":"))+"\n").encode("utf-8")
    if len(data)>1024*1024:
        raise PrivacyReportError("manual_large_report")
    return data,hashlib.sha256(data).hexdigest(),(
        bool(receipt.customer_email_digest) and not has_previous_redaction
    )
