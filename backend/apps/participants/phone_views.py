"""Celular no balcão: busca do participante e cadastro do número pelo lojista.

Somente proprietário/gerente da própria loja. O número nunca volta na resposta
(só os 4 últimos dígitos) e não vira contato comprovado.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantMembership
from .models import ProgramParticipant
from .phone import PhoneConflict, assign_phone, find_participant_by_phone


def _reply(data, status=200):
    result = Response(data, status=status)
    result["Cache-Control"] = "private, no-store"
    return result


def _manager(user, tenant_id):
    membership = get_object_or_404(TenantMembership, user=user, tenant_id=tenant_id)
    return membership.role in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)


def _brief(item):
    return {"id": str(item.id), "display_name": item.display_name,
            "phone_last4": item.phone_last4 or None, "status": item.status}


class ParticipantPhoneLookupView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def post(self, request, tenant_id):
        # POST para o número não ficar em URL, logs de acesso nem histórico.
        if not _manager(request.user, tenant_id):
            return _reply({"detail": "Acesso restrito à administração."}, 403)
        if not isinstance(request.data, dict) or set(request.data) != {"phone"}:
            return _reply({"detail": "Informe somente o celular."}, 400)
        try:
            match = find_participant_by_phone(
                tenant_id=tenant_id, raw=request.data["phone"],
                statuses=[ProgramParticipant.Status.ACTIVE],
            )
        except ValueError as exc:
            return _reply({"detail": str(exc)}, 400)
        return _reply({"match": _brief(match) if match else None})


class ParticipantPhoneView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, tenant_id, participant_id):
        if not _manager(request.user, tenant_id):
            return _reply({"detail": "Acesso restrito à administração."}, 403)
        if (not isinstance(request.data, dict) or set(request.data) != {"phone", "customer_informed"}
                or request.data["customer_informed"] is not True
                or not isinstance(request.data["phone"], str)):
            return _reply({"detail": "Confirme que o próprio cliente informou o celular."}, 400)
        participant = get_object_or_404(
            ProgramParticipant.objects.select_for_update(),
            pk=participant_id, tenant_id=tenant_id,
            status__in=[ProgramParticipant.Status.ACTIVE, ProgramParticipant.Status.PAUSED],
        )
        try:
            assign_phone(participant, request.data["phone"].strip())
        except PhoneConflict as exc:
            return _reply({"detail": str(exc)}, 409)
        except ValueError as exc:
            return _reply({"detail": str(exc)}, 400)
        return _reply({"participant": _brief(participant)})
