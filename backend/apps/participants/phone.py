"""Celular como identificador do cliente no balcão.

O número nunca é salvo em claro: guardamos só o HMAC por loja (mesma chave
dos contatos verificados) e os 4 últimos dígitos para o lojista reconhecer.
Celular informado no caixa NÃO é contato comprovado: não entra em
VerifiedCustomerContact e não resolve pedidos de canais externos.
"""
import re

from apps.customers.services import _digests

DIGITS = re.compile(r"\D+")


class PhoneConflict(ValueError):
    """O mesmo celular já pertence a outro participante desta loja."""


def normalize_br_phone(raw):
    """Aceita (31) 99999-9999, 31999999999, +55 31 99999-9999. Devolve E.164."""
    if not isinstance(raw, str) or len(raw) > 32:
        raise ValueError("Celular inválido.")
    text = raw.strip()
    digits = DIGITS.sub("", text)
    if text.startswith("+"):
        if not digits.startswith("55"):
            raise ValueError("Use um celular do Brasil, com DDD.")
        digits = digits[2:]
    elif len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if len(digits) == 11 and digits[0] == "0":
        raise ValueError("Informe o DDD sem o zero.")
    if len(digits) not in (10, 11):
        raise ValueError("Informe o celular com DDD, por exemplo (31) 99999-9999.")
    ddd = int(digits[:2])
    if ddd < 11 or ddd > 99 or digits[2] == "0":
        raise ValueError("DDD ou número inválido.")
    if len(digits) == 11 and digits[2] != "9":
        raise ValueError("Celular com 11 dígitos precisa começar com 9 depois do DDD.")
    return "+55" + digits


def phone_digests(*, tenant_id, e164):
    """Todos os digests válidos (rotação de SECRET_KEY); o primeiro é o atual."""
    return _digests(tenant_id=tenant_id, kind="phone", value=e164)


def phone_fields(*, tenant_id, raw):
    """Normaliza e devolve (digest atual, últimos 4 dígitos)."""
    e164 = normalize_br_phone(raw)
    return phone_digests(tenant_id=tenant_id, e164=e164)[0], e164[-4:]


def find_participant_by_phone(*, tenant_id, raw, statuses=None):
    from .models import ProgramParticipant
    e164 = normalize_br_phone(raw)
    qs = ProgramParticipant.objects.filter(
        tenant_id=tenant_id,
        phone_digest__in=phone_digests(tenant_id=tenant_id, e164=e164),
    )
    if statuses:
        qs = qs.filter(status__in=statuses)
    return qs.first()


def assign_phone(participant, raw):
    """Grava (ou limpa, com raw vazio) o celular. Exige transação do chamador."""
    from .models import ProgramParticipant
    if raw == "":
        participant.phone_digest, participant.phone_last4 = "", ""
        participant.save(update_fields=["phone_digest", "phone_last4"])
        return participant
    digest, last4 = phone_fields(tenant_id=participant.tenant_id, raw=raw)
    other = ProgramParticipant.objects.filter(
        tenant_id=participant.tenant_id,
        phone_digest__in=phone_digests(tenant_id=participant.tenant_id, e164=normalize_br_phone(raw)),
    ).exclude(pk=participant.pk).exists()
    if other:
        raise PhoneConflict("Este celular já está em outro cadastro do clube.")
    participant.phone_digest, participant.phone_last4 = digest, last4
    participant.save(update_fields=["phone_digest", "phone_last4"])
    return participant


def copy_submission_phone(submission, participant):
    """Leva o celular do formulário de adesão ao participante, sem roubar de outro."""
    from .models import ProgramParticipant
    if not submission.phone_digest or participant.phone_digest:
        return
    if ProgramParticipant.objects.filter(
        tenant_id=participant.tenant_id, phone_digest=submission.phone_digest,
    ).exclude(pk=participant.pk).exists():
        return
    participant.phone_digest = submission.phone_digest
    participant.phone_last4 = submission.phone_last4
    participant.save(update_fields=["phone_digest", "phone_last4"])
