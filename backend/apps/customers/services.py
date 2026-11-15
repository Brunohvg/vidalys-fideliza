"""Serviços internos para identidade verificada. NÃO são endpoints públicos.

Somente adaptadores autenticados ou o fluxo que consumiu um desafio OTP
podem declarar comprovação. Um e-mail digitado em um pedido não é prova.
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant

from .models import ChannelCustomerReference, CustomerProfile, VerifiedCustomerContact


PHONE_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
EXTERNAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
PROOF_METHODS = {"email_otp", "whatsapp_otp", "provider_confirmed"}


class IdentityConflict(ValueError):
    """Vínculos divergentes exigem verificação humana; nunca mesclar automaticamente."""


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError("E-mail inválido.")
    value = value.strip().casefold()
    try:
        validate_email(value)
    except ValidationError as exc:
        raise ValueError("E-mail inválido.") from exc
    if len(value) > 254:
        raise ValueError("E-mail inválido.")
    return value


def normalize_phone(value):
    """Exige E.164 completo; não adivinha DDI nem confunde CPF com telefone."""
    if not isinstance(value, str) or not PHONE_E164.fullmatch(value):
        raise ValueError("Telefone precisa estar em E.164, como +5531999999999.")
    return value


def normalize_checkout_phone(value):
    """Only strip formatting; never infer a missing country code."""
    if not isinstance(value, str):
        raise ValueError("Telefone de checkout inválido.")
    compact = re.sub(r"[\\s().-]", "", value.strip())
    if compact.startswith("55") and not compact.startswith("+"):
        compact = "+" + compact
    return normalize_phone(compact)


def normalize_cpf(value):
    """Valida CPF brasileiro; nenhuma cópia do CPF é persistida."""
    if not isinstance(value, str):
        raise ValueError("CPF inválido.")
    digits = re.sub(r"[.\s-]", "", value)
    if not re.fullmatch(r"[0-9]{11}", digits) or len(set(digits)) == 1:
        raise ValueError("CPF inválido.")
    def digit(n):
        total = sum(int(digits[i]) * (n - i) for i in range(n - 1))
        result = 11 - (total % 11)
        return 0 if result >= 10 else result
    if digit(10) != int(digits[9]) or digit(11) != int(digits[10]):
        raise ValueError("CPF inválido.")
    return digits


def _digests(*, tenant_id, kind, value):
    """Permite rotação de SECRET_KEY enquanto chaves antigas forem mantidas."""
    message = f"{tenant_id}:{kind}:{value}"
    secrets = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return tuple(dict.fromkeys(
        salted_hmac(
            "vidalys.customer-contact.v1", message, secret=secret, algorithm="sha256",
        ).hexdigest()
        for secret in secrets
    ))


def find_verified_customer(*, tenant_id, email=None, phone_e164=None, cpf=None):
    """Consulta interna; só contatos previamente comprovados resolvem perfis."""
    if sum(x is not None for x in (email, phone_e164, cpf)) != 1:
        raise ValueError("Informe exatamente um identificador.")
    if email is not None:
        kind, value = VerifiedCustomerContact.Kind.EMAIL, normalize_email(email)
    elif phone_e164 is not None:
        kind, value = VerifiedCustomerContact.Kind.PHONE, normalize_phone(phone_e164)
    else:
        kind, value = VerifiedCustomerContact.Kind.CPF, normalize_cpf(cpf)
    matches = list(VerifiedCustomerContact.objects.select_related("profile").filter(
        tenant_id=tenant_id,
        kind=kind,
        lookup_digest__in=_digests(tenant_id=tenant_id, kind=kind, value=value),
    ))
    if len({item.profile_id for item in matches}) > 1:
        raise IdentityConflict("Contato duplicado em perfis divergentes.")
    return matches[0].profile if matches else None


@transaction.atomic
def attach_verified_contact(
    *, tenant_id, participant_id, email=None, phone_e164=None, cpf=None, proof_method
):
    """Associa UM contato comprovado à carteira lógica do participante.

    A prova deve ser validada antes pelo chamador (OTP consumido ou
    identidade do provedor autenticada). Não aceitar proof_method de HTTP.
    """
    if sum(x is not None for x in (email, phone_e164, cpf)) != 1:
        raise ValueError("Informe apenas um identificador verificado.")
    if proof_method not in PROOF_METHODS:
        raise ValueError("Origem da comprovação inválida.")
    if cpf is not None and proof_method != "provider_confirmed":
        raise ValueError("CPF exige comprovação de identidade por provedor.")
    if phone_e164 is not None and proof_method == "email_otp":
        raise ValueError("E-mail confirmado não comprova telefone.")
    if email is not None and proof_method == "whatsapp_otp":
        raise ValueError("WhatsApp confirmado não comprova e-mail.")
    if cpf is not None:
        kind, value = VerifiedCustomerContact.Kind.CPF, normalize_cpf(cpf)
    elif email is not None:
        kind, value = VerifiedCustomerContact.Kind.EMAIL, normalize_email(email)
    else:
        kind, value = VerifiedCustomerContact.Kind.PHONE, normalize_phone(phone_e164)
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
    if tenant.status != Tenant.Status.ACTIVE:
        raise IdentityConflict("Loja inativa.")
    participant = ProgramParticipant.objects.select_for_update().get(
        pk=participant_id, tenant=tenant, status=ProgramParticipant.Status.ACTIVE,
    )
    if email is not None and (
        not participant.contact_email
        or normalize_email(participant.contact_email) != value
    ):
        raise IdentityConflict("E-mail divergente do participante já confirmado.")

    digests = _digests(tenant_id=tenant.pk, kind=kind, value=value)
    matches = list(VerifiedCustomerContact.objects.select_related("profile").filter(
        tenant=tenant, kind=kind, lookup_digest__in=digests,
    ))
    if len({item.profile_id for item in matches}) > 1:
        raise IdentityConflict("Contato duplicado em perfis divergentes.")
    contact = matches[0] if matches else None
    current = CustomerProfile.objects.filter(
        tenant=tenant, participant=participant
    ).first()

    if contact and contact.profile.participant_id != participant.pk:
        raise IdentityConflict("Contato já pertence a outra identidade nesta loja.")
    if contact and current and contact.profile_id != current.pk:
        raise IdentityConflict("Perfis divergentes: vinculação exige revisão.")

    if contact:
        return contact.profile, False

    profile = current
    if profile is None:
        profile = CustomerProfile.objects.create(
            tenant=tenant, participant=participant, display_name=participant.display_name,
        )
    VerifiedCustomerContact.objects.create(
        tenant=tenant, profile=profile, kind=kind, lookup_digest=digests[0],
        proof_method=proof_method, verified_at=timezone.now(),
    )
    return profile, True


@transaction.atomic
def attach_channel_reference(*, tenant_id, participant_id, channel, external_id):
    """Somente após o adaptador conferir a vinculação no provedor/autorização."""
    if channel not in ChannelCustomerReference.Channel.values:
        raise ValueError("Canal inválido.")
    if not isinstance(external_id, str) or not EXTERNAL_ID.fullmatch(external_id):
        raise ValueError("ID externo inválido.")
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
    if tenant.status != Tenant.Status.ACTIVE:
        raise IdentityConflict("Loja inativa.")
    participant = ProgramParticipant.objects.select_for_update().get(
        pk=participant_id, tenant=tenant, status=ProgramParticipant.Status.ACTIVE,
    )
    profile = CustomerProfile.objects.filter(
        tenant=tenant, participant=participant,
    ).first()
    if profile is None or not profile.verified_contacts.exists():
        raise IdentityConflict("É necessária identidade de contato verificada.")
    existing = ChannelCustomerReference.objects.filter(
        tenant=tenant, channel=channel, external_id=external_id,
    ).first()
    if existing:
        if existing.profile_id != profile.pk:
            raise IdentityConflict("Referência externa já vinculada a outro cliente.")
        return existing, False
    return ChannelCustomerReference.objects.create(
        tenant=tenant, profile=profile, channel=channel, external_id=external_id,
    ), True
