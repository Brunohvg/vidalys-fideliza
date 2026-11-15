# PR #26 — Liquidação PSP, revogação e gate comercial

Estado: código em PR DRAFT. SEM MIGRAÇÕES/COUPONS/PSP/LOJA real executados. Go-Live NO-GO.

## Contratos implantados em código

1. Origem financeira: GET restrito da charge Pagar.me v5 com Basic Auth em host fixo, não-redirecionável, limitado a 128 KiB, sem retry automático; exige charge.status paid, last_transaction capturada, captura integral, ausência explícita de reembolso e correspondência do código do pedido. Não confundir status da loja com captura PSP. A fonte por tenant comercial NÃO está implantada: apenas credencial sintética QA fixada por tenant no secret manager.
2. Caixa: contrato com valor e horário auditáveis, operador que lançou a venda, segundo aprovador OWNER/ADMIN da mesma loja, identidade e funções distintas. Somente balcão (counter); não aceitar Flow/WhatsApp como caixa automaticamente.
3. Provas: PaymentProofAudit imutável por origem/pedido/evidência, hash HMAC; triggers PostgreSQL UPDATE/DELETE em FinancialEvidence e PaymentProofAudit, sem alterar os históricos existentes. Lançamentos financeiros permanecem no motor loyalty, que exige regra, margem por SKU, orçamento, carência e prova.
4. Fluxo QA fim a fim: settlement_orchestration.settle_qa_nuvemshop_checkout reconsulta PSP por conta QA pinada, registra prova idempotente, liquida o voucher do checkout e concede novo grant em uma transação única sob custos reais. É serviço interno, sem endpoint público. Falha de orçamento/custo reverte voucher+grant, preserva apenas prova append-only. Nuvemshop order/paid isoladamente jamais libera nada.
5. Titularidade: contact_email, contact_phone e contact_identification (CPF) no GET OAuth do pedido devem resolver TODOS ao mesmo perfil que previamente concluiu OTP/identidade provedora. CPF é validado e HMAC por loja; CPF checkout não cria identidade automaticamente. Divergência impede marcar cupom aplicado. Ordem de origem, coupon_id, código e desconto conferidos.
6. Revogação: GET /coupons/{id} com usado=0 e código exato, DELETE uma única vez, GET pós-DELETE para comprovar ausência, com estado de incerteza. Cupom expirado sem pedido, após carência 30m, libera reserva somente se a revogação estiver comprovada e as flags financeiras estiverem liberadas. Cupom de pedido cancelado/estornado associado é revogado, mas a reserva fica retida até prova de que não houve captura (não desenvolvida). Nenhum refund é inventado a partir da Nuvemshop.
7. Celery: nuvemshop-sync isolado dos segredos SMTP, fila nuvemshop; nuvemshop-scheduler/Beat separado sem OAuth nem rede do banco; scan de expiração a cada 15min, no máximo 25 cupons por lote, além de revogação disparada por reconsulta de pedido cancelado. Todos os gates de revogação começam OFF.
8. Ativação: set_loyalty_pilot --mode qa ou --mode commercial com ator superuser, SHA implantado, ticket e aprovação explícita. Commercial exige PostgreSQL, 8 triggers, GET OAuth, read_orders/write_coupons, regra margem/orçamento, custo SKU verificado, PSP por tenant, prova de origem e bloqueio preventivo no checkout.

## Riscos e NO-GO intencionais

- Os sete controles financeiros/PSP/comercial sensíveis estão hardcoded FALSE no backend; não adicionar variável de ambiente para contorná-los em produção.
- Cupom da API Admin Nuvemshop NÃO garante exclusividade do usuário durante a digitação no checkout. Validação POSTERIOR detecta desvio, mas pode não impedir desconto já aplicado. O gate CHECKOUT_OWNER_ENFORCEMENT_VERIFIED permanece False até mecanismo preventivo real validado (por exemplo API de descontos com callback e autenticação suficiente; não presumir que disponível para a loja).
- Uma charge Pagar.me paga NÃO é prova de liquidação de todos os meios de pagamento ou retentativas do pedido; credenciais PSP multi-tenant, conciliação de múltiplas charges/refunds, estorno financeiro e prova de não captura exigem contrato e homologação específica.
- Revogação de pedido cancelado não devolve automaticamente saldo sem prova independente da ausência de captura. Falha remota, timeout, used>0 e ausência de GET confirmatório deixam fundos reservados. Não forçar via SQL nem via admin.
- A existência de um único custo de SKU verificado não comprova a cobertura total dos SKUs do pedido; o motor financeiro exige OrderCosts confirmado. Antes de Go-Live comercial, a cobertura de linhas reais precisa de validação.
- Execução E2E real em Coolify/PG, checkout e PSP ainda é PENDENTE e exige credenciais autorizadas e ambiente de QA; não é substituída pelo CI descartável.
- O GitHub consultado antes do PR indicava homolog em c25d668ec1b668c3a254b816cc96b6236a0dadb2, com PR25 draft. Sem merge, backup, migração ou deploy real neste PR.

## Testes

- apps.loyalty.test_pr26_proof — PSP paid/captured, amount, fraud, caixa duplo, gatilho PG UPDATE/DELETE, comercial NO-GO.
- apps.nuvemshop.test_pr26_revocation — GET used=0, DELETE uma vez, GET 404, devolução de lote reservado após expiração, erro remoto sem devolução, pedido cancelado sem prova financeira.
- apps.loyalty.test_pr26_full_cycle — earn→voucher→cupom→GET pedido→identidade→GET PSP→redeemed + novo grant; repetição idempotente.
- CI GitHub: backend Django/pytest SQLite, PostgreSQL real descartável com triggers, Compose Raw (6 serviços), frontend e 139 testes Playwright. Só declarar aprovação no SHA exato depois de concluir todos jobs.

Referências:
https://docs.pagar.me/reference/obter-cobran%C3%A7a
https://docs.pagar.me/reference/cobran%C3%A7as-1
https://nuvemshop.dev/api/resources/2025-03/coupon
https://nuvemshop.dev/docs-api/resources/2025-03/order
https://nuvemshop.dev/api/resources/2025-03/discounts

Decisão: GO apenas para revisão/QA sintética com flags OFF. NO-GO para dinheiro, Bibelô e qualquer produção.