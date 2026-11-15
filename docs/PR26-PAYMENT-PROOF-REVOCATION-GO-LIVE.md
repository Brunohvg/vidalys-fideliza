# PR #26 — Prova financeira, revogação e gate comercial

**Identificador GitHub:** PR #27 (o número 26 já estava ocupado).
**Estado:** draft; sem execução real, sem merge e sem autorização de fundos.
**Base:** último SHA validado do PR #25.

## Prova PSP independente e caixa

- Cliente `apps/nuvemshop/pagarme_payment.py` faz GET fixo
  https://api.pagar.me/core/v5/charges/{charge_id} com Basic Auth
  usando chave secreta armazenada em secret manager, nunca de entrada HTTP.
  Permite consulta apenas quando
  `FIDELIZA_PAGARME_BOUND_TENANT_ID` coincide com o tenant do pedido.
- Uma resposta só é aceita com status `paid`, `order.code` igual
  à referência exata da venda, `amount == paid_amount` igual aos
  centavos do pedido e `paid_at` com fuso, sem futuro.
  **Não** inferir prova pelo valor, proximidade de horário ou webhook da loja.
- `apps/loyalty/payment_proof.py` registra FinancialEvidence com
  HMAC local + VerifiedPaymentProof ligado ao tenant e evidência.
  A comprovação de caixa `attest_cash_close` exige operador autenticado,
  membership OWNER/ADMIN, recibo único por loja, horário e valor.
  Fechamento manual é atestado humano, NÃO substitui confirmação PSP
  para e-commerce e deve ter procedimento de conferência de caixa real.
- `apply_verified_capture` somente chama o motor de grant e baixa
  do voucher depois de prova com origem autorizada. Não ignora
  custos por variante, margem por pedido, orçamento, carência e
  unicidade do ledger.
- PostgreSQL: migrations de FinancialEvidence, VerifiedPaymentProof,
  CashClosing e confirmação da revogação adicionam 4 triggers bloqueando
  UPDATE/DELETE por SQL direto, para 10 triggers no total.
- `FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED=False` hardcoded; bem como
  flags financeiras globais False e trusted adapters vazio.
  Testes usam override_settings em bases efêmeras. Não expor endpoint de
  escrita financeira ao cliente/lojista nesta etapa.

## Revogação remota antes de devolver os pontos

- `apps/nuvemshop/coupon_client.py`: GET por ID exato e DELETE único
  `/2025-03/{store_id}/coupons/{coupon_id}`, Bearer restrito à loja,
  redirects proibidos, 8s timeout, resposta DELETE 200/204 seguida
  de reconsulta GET de confirmação.
- `coupon_revocation.py`: estado `revoking` antes do request; se houver
  timeout / resposta incerta, voucher fica reservado e **não** devolve
  pontos. Só após API indicar cupom removido ou inválido é gravada
  `NuvemshopCouponRevocationAudit` append-only e executada compensação
  do MESMO lote de pontos/cashback.
- Um cupom usado não é devolvido por mera expiração. Para pedido
  cancelado/estornado, exige vínculo com pedido, status de cancelamento
  obtido pela reconsulta da Nuvemshop e nenhuma captura PSP registrada;
  cupom já liquidado exige tratamento de estorno próprio.
- O worker Nuvemshop isolado tem scanner de expiração limitado a 20
  vouchers por execução. Agendamento Celery Beat só roda se o Beat estiver
  efetivamente implantado; flags financeiras fechadas tornam a tarefa
  inerte no ambiente atual.
- Os estados `revoking`, `issued`, `uncertain` e `applied`
  impedem devolver crédito sem confirmação externa.

## Identidade do comprador

- Em `_paid_coupon_from_order` todos os contatos informados no checkout
  e customer (e-mail e telefone) devem corresponder ao MESMO perfil
  previamente verificado via OTP. Contact divergente/desconhecido bloqueia
  confirmação interna, e nenhuma carteira é transferida por número de pedido.
- **Limitação real de segurança:** esta validação é posterior ao checkout.
  Um cupom da API tradicional é um código reutilizável por qualquer pessoa
  que o conheça até seu uso único; a validação posterior impede baixar
  pontos em titular incorreto, mas **não impede o desconto indevido de ser
  aplicado durante o checkout**. CPF não tem fonte verificada própria no
  Unified ID atual e não deve ser usado como prova inventada.
  Uma restrição de identidade efetiva ANTES de aplicar o desconto deve
  ser homologada usando capacidade contratual disponível no checkout.
  **NO-GO comercial enquanto isso não estiver resolvido.**

## Comando de liberação

`python manage.py set_loyalty_release --mode qa|commercial`
- QA delega ao `set_loyalty_pilot` (apenas homolog).
- Commercial exige production, UUID de tenant aprovada por secret manager,
  SHA implantado, ticket, superuser, confirmação explícita, todas as flags
  financeiras/PSP habilitadas, 10 triggers PG ativas, runtime sem TRUNCATE
  e sem ownership das tabelas, FKs válidas, OAuth read_orders + write_coupons
  provado por GET real e regra vigente com nível inicial, orçamento e custo
  unitário por SKU verificado.
- A versão atual mantém flags hardcoded OFF, então o comando comercial
  recusa a operação: preflight não é um interruptor que contorna bloqueios.

## Testes e critérios de saída

`backend/apps/loyalty/test_pr26_payment_proof.py`: consulta PSP legítima,
  status não pago, dados de outra loja, idempotência, fechamento autenticado,
  SQL UPDATE/DELETE PostgreSQL.
`backend/apps/nuvemshop/test_pr26_revocation.py`: DELETE + reconsulta
  antes da devolução; timeout mantém reserva; comprador divergente não
  captura cupom. Tests/CI também exercitam o ledger anterior.
`.github/scripts/ci_single_compose.py`: roda a suíte PR26 em PostgreSQL
  descartável sem acesso Coolify.

Não executar coupon DELETE, GET com secret PSP ou fechamento de caixa real
contra a Bibelô sem autorização e E2E de loja QA. Também não houve backup,
migração ou deploy real neste PR.

**GO técnico para revisão:** CI 6/6 no SHA final, auditoria dos testes PG.
**GO comercial:** NÃO AUTORIZADO até comprovação real PSP, validação
pré-checkout de titularidade, revogação em loja QA com caso de cancelamento,
reconciliação dos PRs empilhados com `homolog`, backup e E2E remoto.
