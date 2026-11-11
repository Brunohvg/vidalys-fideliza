"""Entrega de relatório de acesso ao titular via painel autenticado da loja.

POST exporta arquivo JSON em memória; POST de confirmação registra que o
próprio administrador baixou a versão exata, sem expor conteúdo em logs.
A confirmação de relatório não conclui uma exclusão LGPD.
"""
import hmac
import re

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant, TenantMembership
from .privacy_models import PrivacyWebhookRequest
from .privacy_reporting import PrivacyReportError, build_customer_report

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _secure(response):
    response["Cache-Control"]="private, no-store, max-age=0"
    response["Pragma"]="no-cache"
    response["Referrer-Policy"]="no-referrer"
    response["X-Robots-Tag"]="noindex, nofollow"
    response["X-Content-Type-Options"]="nosniff"
    return response


def _owner(request, tenant_id):
    member=get_object_or_404(
        TenantMembership, user=request.user, tenant_id=tenant_id,
    )
    return member.role in (TenantMembership.Role.OWNER,TenantMembership.Role.ADMIN)


def _get_request(tenant_id, request_id):
    return get_object_or_404(
        PrivacyWebhookRequest,
        tenant_id=tenant_id, pk=request_id,
        topic=PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST,
    )


class PrivacyReportDownloadView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=["post","options"]

    @transaction.atomic
    def post(self, request, tenant_id, request_id):
        if not _owner(request,tenant_id):
            return _secure(Response({"detail":"Apenas administradores podem consultar relatórios."},
                                    status=403))
        if not isinstance(request.data,dict) or request.data:
            return _secure(Response({"detail":"Esta ação não recebe dados pessoais."},status=400))
        Tenant.objects.select_for_update().get(pk=tenant_id)
        receipt=get_object_or_404(
            PrivacyWebhookRequest.objects.select_for_update(),
            tenant_id=tenant_id, pk=request_id,
            topic=PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST,
        )
        if receipt.state != PrivacyWebhookRequest.State.PENDING:
            return _secure(Response({"detail":"A solicitação não está aguardando relatório."},
                                    status=409))
        try:
            data,sha,complete=build_customer_report(receipt)
        except PrivacyReportError:
            return _secure(Response({"detail":"O relatório requer análise da equipe responsável."},
                                    status=409))
        receipt.report_digest=sha
        receipt.report_accessed_at=timezone.now()
        receipt.report_accessed_by=request.user
        receipt.save(update_fields=["report_digest","report_accessed_at","report_accessed_by"])
        response=HttpResponse(data,content_type="application/json; charset=utf-8")
        response["Content-Disposition"]=(
            f'attachment; filename="relatorio-fideliza-{receipt.id}.json"'
        )
        response["X-Fideliza-Report-Digest"]=sha
        response["X-Fideliza-Report-Complete"]="true" if complete else "false"
        return _secure(response)


class PrivacyReportConfirmView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=["post","options"]

    @transaction.atomic
    def post(self, request, tenant_id, request_id):
        if not _owner(request,tenant_id):
            return _secure(Response({"detail":"Apenas administradores podem confirmar relatórios."},
                                    status=403))
        if (not isinstance(request.data,dict) or set(request.data)!={"confirm","digest"}
                or request.data.get("confirm") is not True
                or not isinstance(request.data.get("digest"),str)
                or not SHA256_RE.fullmatch(request.data["digest"])):
            return _secure(Response({"detail":"Confirme o relatório que recebeu."},status=400))
        Tenant.objects.select_for_update().get(pk=tenant_id)
        receipt=get_object_or_404(
            PrivacyWebhookRequest.objects.select_for_update(),
            tenant_id=tenant_id,pk=request_id,
            topic=PrivacyWebhookRequest.Topic.CUSTOMER_DATA_REQUEST,
        )
        if receipt.state!=PrivacyWebhookRequest.State.PENDING:
            return _secure(Response({"detail":"Esta solicitação não está pendente."},status=409))
        if not receipt.customer_email_digest:
            return _secure(Response({
                "detail":"O relatório não reúne dados suficientes para encerrar a solicitação."
            },status=409))
        if (not receipt.report_digest or not receipt.report_accessed_at
                or receipt.report_accessed_by_id!=request.user.pk
                or not hmac.compare_digest(receipt.report_digest,request.data["digest"])):
            return _secure(Response({
                "detail":"Baixe a versão atual do relatório antes de confirmar seu recebimento."
            },status=409))
        try:
            _,current_digest,complete=build_customer_report(receipt)
        except PrivacyReportError:
            return _secure(Response({"detail":"Os dados mudaram; nova revisão necessária."},
                                    status=409))
        if not complete or not hmac.compare_digest(current_digest,receipt.report_digest):
            return _secure(Response({
                "detail":"Os dados foram atualizados. Baixe novamente o relatório."
            },status=409))
        receipt.state=PrivacyWebhookRequest.State.COMPLETED
        receipt.reason_code="merchant_confirmed_download"
        receipt.processed_at=timezone.now()
        receipt.delivery_confirmed_by=request.user
        receipt.save(update_fields=[
            "state","reason_code","processed_at","delivery_confirmed_by"
        ])
        return _secure(Response({
            "status":"completed",
            "message":"Recebimento do relatório confirmado e registrado.",
        }))
