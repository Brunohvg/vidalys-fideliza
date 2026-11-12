# Integração Vidalys Flow ↔ Vidalys Fideliza — proposta técnica

Data: 11/11/2026 · **Planejamento, não integração ativa**.
Objetivo: fidelizar compradores de vendas pelo WhatsApp e permitir que um
mesmo programa futuramente recompense compras por loja virtual, física e
WhatsApp, sem duplicar crédito ou misturar bases de clientes.

## Diagnóstico em repositórios

Repositório `Brunohvg/vidalys-flow`, branch `main`:
- `apps/orders/models.py`: Order vinculado a Organization, Customer,
  canal, itens e total; estados `draft`, `confirmed`, `cancelled`.
- `apps/payments/models.py`: PaymentIntent com estados
  `pending`, `awaiting_payment`, `processing`, `paid`,
  `cancelled`, `expired`, `requires_attention`.
- `apps/payments/events.py`: evento interno `payment.status_changed`.
- `apps/integrations/models.py`: egress/ingress, leases, attempts,
  idempotência e retries.
- `docs/domains/PAYMENTS.md`: na main consultada, providers reais e
  callbacks permanecem dependentes de aprovação/ativação. **A existência
  do estado paid não prova que a cobrança real esteja ativa.**
- `docs/domains/INTEGRATIONS_VISION.md`: integração concreta exige
  contrato/versionamento e avaliação separada. O adapter de referência
  não é uma integração Flow→Fideliza pronta.

Repositório `Brunohvg/vidalys-fideliza`, branch `homolog`:
- Tenant/ProgramParticipant têm UUIDs internos independentes de
  plataforma, e wallet/ledger têm idempotência.
- A origem de clientes/pedidos ainda é específica da Nuvemshop;
  **crédito por pagamento real não está ativado**.

## Papel de cada sistema

**Flow é o sistema de vendas e pagamentos.** Consolida pedido,
status de pagamento e cancelamento com fonte autoritativa.

**Fideliza é o sistema de relacionamento/recompensas.** Gerencia
participação consentida, elegibilidade, regra por loja, limites de
rentabilidade, carteira e estornos.

**Não compartilhar banco, sessão nem credenciais.** Integrar por
eventos autenticados ou API versionada, com registro durável e
reconciliação.

## Primeiro contrato proposto: `flow.order_paid.v1`

Emissão somente após consulta/validação do `PaymentIntent` autoritativo
em `paid`, Order confirmado, valor/moeda correspondentes e
`requires_attention` ausente. O evento transportaria somente:
- `event_id` (imutável), `schema_version` = 1,
  `occurred_at` ISO-8601;
- `flow_organization_id` + `flow_order_id`;
- `flow_customer_id` (identificador opaco, sem e-mail/telefone/documento);
- `paid_amount_cents`, `currency=BRL`, `payment_id`,
  `paid_at`, `channel=whatsapp`;
- `source_system=vidalys_flow`.

A assinatura deve cobrir o body bruto, incluir chave específica
por instalação/loja e ter verificação de tempo/replay. Evitar
dados pessoais no payload e nos logs.

Recepção pelo Fideliza:
1. Resolver a integração via credencial/assinatura, **não** confiar no
   tenant informado no payload.
2. Validar mapeamento `Flow.Organization ↔ Fideliza.Tenant`.
3. Confirmar identidade e aceite explícito do Customer para o programa;
   um número WhatsApp sozinho não prova identidade nem consentimento.
4. Validar evento e, conforme o caso, reconciliar com a origem antes
   de conceder qualquer benefício.
5. Idempotência por `integration_id + flow_order_id + benefit_rule`.
6. Guardar venda normalizada por canal e status financeiro, evitando
   conceder por link criado, pedido aberto ou mensagem enviada.
7. Aplicar teto e condições de margem antes de criar lançamento imutável.
8. Bloquear duplicações se a mesma compra chegou também pelo ERP/
   Nuvemshop (mapeamento canônico cross-channel).
9. Registrar cancelamentos, estornos, chargebacks e eventual expiração;
   nenhum cashback liberado antes da regra de prazo de segurança.
10. Outbox/retry/backoff, dead-letter e reconciliação por período.

## Eventos futuros

- `flow.order_cancelled.v1`: anular benefício ainda pendente;
- `flow.payment_refunded.v1`: estornar crédito disponível/pendente
  com trilha de auditoria;
- `flow.customer_consent_verified.v1`: opcional, somente com prova
  explícita de aceite do regulamento do Fideliza;
- `fideliza.benefit_available.v1`: retorno ao Flow para que a própria
  infraestrutura de comunicação autorizada envie aviso por WhatsApp,
  respeitando consentimento e bloqueio de mensagens.

Não enviar promoções para números que só apareceram em conversas.

## UX do lojista

Conexões mostradas por **canal**: Nuvemshop, Flow (WhatsApp),
loja física/PDV e outros futuros conectores. Mostrar estado real
(conectado/em preparação), não parâmetros técnicos, tokens ou nomes
de webhooks. Um lojista com os dois sistemas não deve cadastrar o
mesmo cliente duas vezes sem validação de identidade.

## Fases recomendadas

1. **Agora:** terminar teste visual e jornada de homologação da
   Nuvemshop; não alterar o motor financeiro nesta etapa.
2. Criar integração `flow` desativada por padrão, mapeamento
   Organization↔Tenant e contrato assinado em testes sintéticos.
3. Implementar leitura de pagamentos realmente confirmados, com
   idempotência e consentimento verificável, em homologação.
4. Testar cancelamento, reembolso, duplicidade, entrega fora de
   ordem e falha parcial antes de habilitar benefícios.
5. Ativar comunicação de benefícios no Flow com opt-in e controle LGPD.
6. Generalizar o mesmo contrato para POS/ERP e outros ecommerce.

**Não implementado nesta decisão:** endpoint real, OAuth/sincronização,
credencial Flow, callback Pagar.me, criação de crédito ou alteração na
loja de qualquer usuário. Os dois projetos seguem isolados.
