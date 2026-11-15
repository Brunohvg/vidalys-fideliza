# PR #23 — Conformidade financeira, vouchers publicados e PDV unificado

Referência: PR #23 empilhado em PR #22. Não existe merge em homolog nem deploy,
e nenhum dos switches financeiros foi habilitado. O efeito nos dados da Bibelô
é **zero** até a execução explicitamente autorizada das migrações no Coolify.

## 1. P0 — cashback por origem (wallets + loyalty)

- O crédito \`CashbackEvent(kind=accrual)\` é a origem imutável de um
  \`LoyaltyGrant.cashback_event\`. Por definição, cada grant aponta a um
  único evento de crédito por venda.
- \`CashbackOriginEntry\` armazena eventos compensatórios por
  \`origin_event_id\`, bucket e delta assinado. Todos os movimentos de
  um grant (release/reserve/cancel/redeem/refund) exigem essa origem.
- \`origin_balances(origin_event)\` usa SUM sobre os lançamentos da
  concessão original; NÃO utiliza o saldo total da carteira para apurar
  quanto debitar de outra compra.
- \`VoucherCashbackAllocation\` registra a distribuição de uma reserva
  entre origens. Reserva de múltiplas compras gera lançamentos separados
  e idempotentes; cancelamento e consumo preservam o rateio.
- \`reverse_grant\` cancela apenas vouchers que utilizavam o lote de
  pontos ou crédito de cashback dessa concessão. Qualquer valor da
  origem já resgatado vira \`LoyaltyRecovery\` e não reduz valores de
  outras vendas. O estorno exige \`FinancialEvidence(kind=refund)\`
  de adaptador PSP autorizado, ainda inexistente em produção.

Testes: uma compra A, uma compra B, reserva e consumo do cashback de A,
estorno de A → B mantém seu saldo e o valor resgatado entra em recovery.
Os ledgers antigos de teste sem alocação por origem não são migrados
silenciosamente para origens inventadas: fluxo bloqueia em caso de
alocação insuficiente. Validação de históricos legados deve ser revisada
antes de qualquer ativação real.

## 2. P0 — triggers PostgreSQL

- \`points/migrations/0002_immutable_postgres_ledger.py\` protege
  \`points_pointlot\`, \`points_pointevent\` e \`points_pointentry\`.
- \`wallets/migrations/0003_immutable_postgres_ledger.py\` protege
  \`wallets_cashbackevent\`, \`wallets_cashbackentry\` e
  \`wallets_cashbackoriginentry\`.
- Triggers BEFORE UPDATE/DELETE FOR EACH ROW lançam erro SQLSTATE 23514.
  Correções exigem INSERT de eventos compensatórios; rollback de
  migration remove triggers por passo explícito e auditado.
- Não é possível considerar append-only resistente a DBA/superuser:
  o papel de aplicação deve ser não-superuser, sem privilégios DDL,
  sem \`TRUNCATE\`, sem \`DISABLE TRIGGER\`. Triggers não impedem TRUNCATE;
  não conceder esse privilégio à role da API.
- SQLite não implementa triggers PostgreSQL; somente o CI externo com
  Postgres executa testes de QuerySet.update e SQL UPDATE/DELETE cru.

## 3. P0 — reward_id em vez de valores arbitrários

- \`POST /api/v1/public/clubs/{slug}/vouchers/issue/\` aceita
  **somente** \`{"reward_id": "<uuid>"}\`. Nunca aceita \`unit\`,
  \`amount\` ou preço fornecidos pelo navegador.
- O motor bloqueia recompensa rascunho, não publicada, fora do prazo,
  limite de vouchers não cancelados atingido, canal não homologado,
  preço/desconto incoerentes, sem carteira com saldo suficiente
  ou com pendência financeira. Todos os checks são transacionais sob
  lock por tenant e recompensa.
- \`LoyaltyVoucher\` mantém FK da recompensa e snapshots de desconto,
  pontos/cashback necessários, pedido mínimo e canais; lotes e
  origens têm reservas individuais.
- **Regra impossível de antecipar:** o valor real de um *próximo
  pedido* ainda não existe ao emitir um voucher de desconto. O backend
  valida a configuração do mínimo na emissão, mas o mínimo da compra
  é verificado NA UTILIZAÇÃO, quando recebe \`sale_id\` e
  \`capture_evidence_id\`, confere canal, identidade, pedido posterior
  ao voucher e \`FinancialEvidence\` independente.
- \`POST /api/v1/tenants/{id}/loyalty/vouchers/redeem/\` agora exige
  \`code\`, \`redemption_reference\`, \`sale_id\`,
  \`capture_evidence_id\`. Texto livre nunca comprova pagamento.
- Nenhum endpoint cria cupom Nuvemshop: \`external_coupon_created=false\`.
  Estados de recompensa publicada ainda são informativos até a
  homologação PSP e checkout de verdade.
- A gestão comercial atual de catálogo mantém padrões de canal,
  validade opcional e unit=points. Editor avançado de validade/canais
  continua como evolução de produto, não como condição de segurança:
  defaults são validados e modificações futuras só podem vir de
  operador autorizado.

## 4. P1 — PDV compartilha ingestão, com vínculo tardio auditado

- \`POST /api/v1/tenants/{id}/sales/manual/\` mantém contrato
  compatível com o React, mas encaminha seu comando para
  \`channels.services.ingest_order_event(..., manual_override=...)\`.
- O serviço cria \`SaleRecord\` e \`SaleEventReceipt\` como os demais
  canais, com status \`paid\` **informado**, e ID de evento persistente.
  Valor do balcão é registrado, mas isso NÃO autoriza points/wallets.
- Sem cliente: perfil não é criado ficticiamente; estado permanece
  \`awaiting_member\`; identificação fica pendente.
- Após prova de contato verificado em \`customers\`, administrador
  usa \`POST /api/v1/tenants/{id}/sales/manual/{sale_id}/link/\` com
  \`participant_id\`. Serviço transacional \`sales/services.py\`
  trava o tenant, valida participação/OTP, vincula o perfil sem
  mudar o evento anterior, e cria \`SaleManualLinkAudit\` 1:1.
- Na tela de histórico há opção "Vincular cliente confirmado".
  A conferência operacional continua possível para loja com
  uma única pessoa; não vira prova financeira nem crédito.

## 5. Migração e release

Migrações novas, para ordem do grafo do Django:
- \`wallets/0002_cashback_origin_entries\`
- \`wallets/0003_immutable_postgres_ledger\`
- \`points/0002_immutable_postgres_ledger\`
- \`sales/0005_reward_redemption_terms\`
- \`sales/0006_counter_identity_link\`
- \`loyalty/0002_voucher_reward_origin\`
- \`loyalty/0003_voucher_redemption_evidence\`

Todas são *schema-only*, sem preenchimento de créditos, sem replay de
pedidos, sem concessão automática e sem publicação de cupons.

A validação de scripts e smoke CI em banco efêmero não substitui a
homologação externa. Manter a sequência de PR #18 → #19 → #20 →
#21 → #22 → #23. Antes do primeiro migrate real:
dump protegido, checksum, teste de restore em base scratch, autorização,
janela de manutenção, verificação Django + FK e testes ponta a ponta.
A API deve continuar com \`migrate --check\` no boot (PR #22),
sem migração automática no início do container.

Os gates \`FIDELIZA_POINTS_WRITES_ENABLED\`,
\`FIDELIZA_LEDGER_WRITES_ENABLED\` e
\`FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED\` continuam FALSE.
\`FIDELIZA_TRUSTED_PAYMENT_ADAPTERS\` permanece vazio.
