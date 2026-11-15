# PR #25 — Nuvemshop OAuth, cupom único e ativação QA

**Estado: código de PR, financeiro desligado e implantação real não comprovada.**
O GitHub consultado durante este corte ainda mostra homolog no SHA
c25d668ec1b668c3a254b816cc96b6236a0dadb2 e PRs #23/#24 não
mesclados. Sem acesso administrativo ao Coolify/PG, não afirmar E2E real.

## Contrato de ativação

- Tenant.loyalty_live_enabled = False para toda loja por padrão.
- Esta flag não é escrita por OAuth, migration, cadastro ou PATCH de
  configurações. O painel apenas exibe o status.
- A ativação exige comando auditado exclusivo de loja QA com slug qa-
  ou homolog-, operador superusuário, ticket, confirmação, SHA do código
  implantado e aprovação de ambiente; lojas com nome Bibelô bloqueadas.
- A flag por loja é apenas autorização preparatória. Três flags financeiras
  globais são hardcoded FALSE em config/settings.py; adaptadores PSP
  confiáveis são conjunto vazio. Por isso NÃO é possível criar cupons
  econômicos nem emitir vouchers reais com o código atual.
- Também requer explicitamente: read_orders, write_coupons, HMAC webhooks,
  reconsulta OAuth, outbound de cupons e consentimento do cliente no clube.

## OAuth e cupons

- O token OAuth criptografado pertence à instalação exata de cada loja.
  read_orders + write_coupons exigem consentimento e reinstalação;
  nenhum scope concedido sozinho habilita operação monetária.
- Cupom: API Admin 2025-03 POST /coupons com code alfanumérico,
  type absolute, value monetário, min_price, max_uses 1,
  end_date YYYY-MM-DD, end_time HH:MM UTC, sem frete nem acumulação.
  A implementação valida as condições da resposta remota.
- NuvemshopCouponIntent: one-to-one por voucher, código Fernet cifrado,
  hash de controle, ID remoto e estados prepared/uncertain/issued/
  applied_pending_proof/settled. Reserva por grant/lote necessária.
- POST é no máximo uma tentativa, inclusive se HTTP timeout. Em resultado
  desconhecido, as próximas tentativas fazem apenas GET por código exato
  (sem segundo POST), com revisão manual se não encontrado.
- Voucher com cupom externo pendente NÃO pode ter suas reservas liberadas
  por simples cancelamento; desativação de tenant fica bloqueada se houver
  cupom externo pendente.
- O motor também impede emitir outro voucher Nuvemshop para o mesmo
  participante enquanto existir uma reserva de loja virtual ativa;
  um reenvio HTTP não pode reservar novos lotes criando outro código.

## Webhook e conciliação financeira

- Webhook HMAC order/paid ou order/updated registra apenas identificadores
  em inbox idempotente, sem PII e sem crédito.
- Após a inbox HMAC confirmar e gravar o evento, o serviço agenda
  uma tarefa Celery na fila exclusiva nuvemshop (se o gate estiver ON).
  O worker nuvemshop-sync, distinto do worker SMTP, tem somente os segredos
  OAuth e as permissões de leitura necessárias; nunca recebe credenciais
  SMTP nem flags financeiras. Reentregas são idempotentes e falhas
  transitórias têm backoff/retry limitados; estados contraditórios exigem
  revisão humana.
- O comando manual recheck_nuvemshop_inbox no container API permanece
  como recuperação da fila de eventos e operação QA autorizada.
- Reconsulta GET /orders/{id} da loja exata, com fields fixos,
  normalização BRL, checagem de status e Unified ID do contato
  previamente validado via OTP; ingestion via channels.services.
- Coupon ID, código, valor de desconto, valor mínimo e titular
  verificados. Ao receber evento pago, a intenção de cupom vai somente
  para applied_pending_proof; LoyaltyVoucher fica reserved.
- A baixa definitiva requer FinancialEvidence independente de PSP,
  conferida por loyalty.services.redeem_voucher; só então
  settle_coupon_after_psp_capture marca SETTLED. Um status pago informado
  pela Nuvemshop ou pagamento marcado manualmente NÃO é prova do PSP.
- Pendente para liberar dinheiro: PSP real autenticado, revogação externa
  de cupom e tratamento robusto de cancelamentos/reembolsos, testes de
  frete/min_price em checkout real com transação QA e acesso autorizado.

## Execução operacional (somente se a homolog real for confirmada)

No shell privado do container API, com ambiente homolog, checkout e
autorização de operador, nunca com dados ou credenciais no PR:

    export FIDELIZA_ENVIRONMENT=homolog
    export FIDELIZA_PILOT_ACTIVATION_APPROVAL=YES_VERIFIED_QA_ONLY
    export FIDELIZA_DEPLOYED_SHA=SHA_COMPLETO_DO_DEPLOY
    uv run --locked python manage.py set_loyalty_pilot \
      --tenant-id UUID_QA --actor-id ID_DO_SUPERUSER \
      --ticket QA-PR25-APROVADO --approved-sha SHA_COMPLETO_DO_DEPLOY \
      --enable --confirm ENABLE_QA_ONLY

A desativação usa --disable e --confirm DISABLE_QA_ONLY, exigindo
revisão prévia de cupons externos em uso.

Para reconsulta QA, após habilitar as flags de preview, webhook e
order recheck SOMENTE em homologação com aprovação separada:

    export FIDELIZA_NUVEMSHOP_RECHECK_APPROVED=YES_QA_REREAD
    uv run --locked python manage.py recheck_nuvemshop_inbox \
      --tenant-id UUID_QA --limit 10 --apply-qa

O comando de reconsulta processa no máximo 30 eventos, resgatáveis
pela inbox e sem alegação de captura. Ajustar credenciais via secret
manager e manter FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=0.

## Validação da implantação

Antes de qualquer liberação, executar os scripts do PR #24:
- scripts/homolog_http_smoke.py para HTTP externo e ingestão QA;
- backend/scripts/homolog_smoke_db_audit.py para Unified ID + 0 grant;
- backend/scripts/homolog_post_migrate_check.py para os triggers PG;
- frontend/homolog/live-portal.spec.ts sem mocks, com sessão QA privada.

**GO para aceitar código:** CI 6/6 verde no SHA exato e revisão técnica,
  inclusive isolamento do quinto serviço OAuth nuvemshop-sync.
**GO financeiro:** ainda BLOQUEADO por ausência de PSP independente
e E2E autorizado do checkout. Nenhum procedimento deste PR concede
saldo à Bibelô.

Referências oficiais:
https://nuvemshop.dev/api/resources/2025-03/coupon
https://nuvemshop.dev/docs-api/resources/2025-03/order
