"""Painel: cadastrar cliente manualmente e remover cliente. Só proprietário e administrador."""
import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.tenants.models import Tenant, TenantMembership
from .detail_views import VISIBLE, _detail, _private
from .models import ProgramParticipant

MANAGERS = (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


def _manager(request, tenant_id):
    member = get_object_or_404(TenantMembership.objects.select_related("tenant"), tenant_id=tenant_id, user=request.user)
    return member if member.role in MANAGERS else None


class ParticipantCreateView(APIView):
    """Cadastro pela loja, com a autorização da cliente declarada por quem cadastra.

    A participação já fica ativa (o balcão encontra pelo celular). A cliente recebe um e-mail
    para confirmar: só depois disso as compras no site com aquele e-mail geram saldo e ela
    entra no Meu Clube. Mesmo e-mail já no clube: não cria outra pessoa.
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id):
        member = _manager(request, tenant_id)
        if member is None:
            return _private({"detail": "Somente administradores cadastram clientes."}, 403)
        data = request.data
        allowed = {"name", "email", "phone", "authorized"}
        if not isinstance(data, dict) or not {"name", "email", "authorized"} <= set(data) <= allowed:
            return _private({"detail": "Informe nome, e-mail e a autorização da cliente."}, 400)
        name, email, phone = data.get("name"), data.get("email"), data.get("phone", "")
        if data.get("authorized") is not True:
            return _private({"detail": "Confirme que a cliente autorizou entrar no clube."}, 400)
        if not isinstance(name, str) or not 3 <= len(name.strip()) <= 140 or any(ord(c) < 32 for c in name):
            return _private({"detail": "Informe o nome da cliente."}, 400)
        email = email.strip().casefold() if isinstance(email, str) else ""
        try:
            validate_email(email)
        except ValidationError:
            return _private({"detail": "Informe um e-mail válido."}, 400)
        if not isinstance(phone, str) or len(phone) > 32:
            return _private({"detail": "Celular inválido."}, 400)
        from .enrollment_models import EnrollmentEmailChallenge, EnrollmentInvite, EnrollmentSubmission
        from .email_proof import email_links_enabled, enqueue_confirmation
        from .phone import PhoneConflict, assign_phone
        from .public_registration_views import active_terms_for, is_ready
        with transaction.atomic():
            tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
            if tenant.status != Tenant.Status.ACTIVE:
                return _private({"detail": "Empresa não está ativa."}, 409)
            terms = active_terms_for(tenant)
            if not is_ready(terms):
                return _private({"detail": "Publique o regulamento do clube antes de cadastrar clientes."}, 409)
            existing = ProgramParticipant.objects.filter(tenant=tenant, contact_email__iexact=email,
                                                         status__in=VISIBLE).first()
            if existing:
                return _private({"detail": "Esta cliente já está no clube.", "participant_id": str(existing.pk)}, 409)
            now = timezone.now()
            participant = ProgramParticipant.objects.create(
                tenant=tenant, external_customer_id=None, display_name=name.strip(), contact_email=email,
                consent_at=now, consent_channel=ProgramParticipant.ConsentChannel.MERCHANT_ASSISTED,
                terms_version=terms.version, status=ProgramParticipant.Status.ACTIVE)
            if phone.strip():
                try:
                    assign_phone(participant, phone)
                except PhoneConflict:
                    transaction.set_rollback(True)
                    return _private({"detail": "Este celular já pertence a outra cliente desta loja."}, 409)
                except ValueError as exc:
                    transaction.set_rollback(True)
                    return _private({"detail": str(exc)}, 400)
            submission = EnrollmentSubmission.objects.filter(
                tenant=tenant, email__iexact=email, withdrawn_at__isnull=True, participant__isnull=True,
            ).order_by("-accepted_at").first()
            if submission is None:
                token = secrets.token_urlsafe(32)
                invite = EnrollmentInvite.objects.create(
                    tenant=tenant, terms=terms, token_digest=hashlib.sha256(token.encode()).hexdigest(),
                    created_by=request.user, expires_at=now + timedelta(hours=24), consumed_at=now)
                consent_text = (terms.body + "\n" + terms.privacy_notice).encode("utf-8")
                submission = EnrollmentSubmission.objects.create(
                    tenant=tenant, invitation=invite, terms=terms, name=name.strip(), email=email, accepted_at=now,
                    terms_digest=hashlib.sha256(consent_text).hexdigest(),
                    phone_digest=participant.phone_digest, phone_last4=participant.phone_last4)
            submission.participant = participant
            submission.save(update_fields=["participant"])
            confirmed = submission.email_verified_at is not None
            if not confirmed and email_links_enabled():
                enqueue_confirmation(submission, EnrollmentEmailChallenge.Purpose.VERIFY)
        if confirmed:
            from apps.sales.online import queue_credit_since_join
            queue_credit_since_join(participant.pk)
        detail = _detail(participant)
        detail["email_confirmation"] = "confirmed" if confirmed else "sent"
        return _private(detail, 201)


class ParticipantRemoveView(APIView):
    """Remove a cliente do clube: zera o saldo, cancela cupom do site e apaga os dados pessoais."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id, participant_id):
        member = _manager(request, tenant_id)
        if member is None:
            return _private({"detail": "Somente administradores removem clientes."}, 403)
        data = request.data
        if not isinstance(data, dict) or data.get("confirm") is not True or not set(data) <= {"confirm", "reason"}:
            return _private({"detail": "Confirme a remoção."}, 400)
        participant = get_object_or_404(ProgramParticipant, pk=participant_id, tenant_id=tenant_id, status__in=VISIBLE)
        from .removal import RemovalBlocked, remove_participant
        try:
            out = remove_participant(participant, actor=request.user, reason=str(data.get("reason", ""))[:240])
        except RemovalBlocked as exc:
            return _private({"detail": str(exc)}, 409)
        return _private({"removed": True, "reversed": out["reversed"], "data_result": out.get("data_result", "erased")})
