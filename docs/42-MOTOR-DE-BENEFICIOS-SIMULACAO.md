# 42 — Motor de benefícios, estágio 1: avaliação pura sem crédito

O motor começa pela mesma entidade CampaignDraft já existente, para
não duplicar a configuração de campanhas entre Telas de Programas,
Rentabilidade e Configurações. Este primeiro contrato tem somente
cashback percentual simulado; pontos, brindes e vouchers ainda não
foram cadastrados/ativados. Não é uma carteira financeira.

Nova API para um rascunho da própria loja:
POST /api/v1/tenants/{tenant_id}/campaign-drafts/{draft_id}/simulate/

Exemplo de cenário sintético:
{"order_amount_cents":15000,"prior_paid_orders":1,"committed_budget_cents":0}

Campos:
- order_amount_cents: valor em centavos da compra hipotética.
- prior_paid_orders: quantas compras anteriores hipoteticamente pagas.
- days_since_last_paid_order: dias de inatividade hipotéticos (reativação).
- committed_budget_cents: parcela de orçamento hipoteticamente usada.

Objetivos:
- second_purchase: exatamente uma compra anterior.
- recurrence: pelo menos duas compras anteriores.
- reactivation: ao menos uma compra anterior e 60 dias sem comprar.
  60 dias é parâmetro técnico provisório, sujeito a configuração antes
  da oferta comercial final.

O avaliador é determinístico, usa apenas inteiros, aplica o mesmo
arredondamento do planejamento de campanhas e recusa recompensa que
ultrapassaria o saldo de orçamento estimado. Não concede uma fração
de benefício quando o orçamento seria insuficiente.

Respostas têm códigos de estado (hypothetical_match, goal_not_met,
budget_insufficient, reward_below_one_cent), projeção de custo e
mensagens explícitas: mode simulation_only, activation_available false,
requires_independent_payment_reconciliation true,
credit_eligible false, ledger_writes_performed 0.

Provas que ainda faltam para o motor real:
- Fatos de compra imutáveis e verificados via Nuvemshop e PSP.
- Cálculo de base elegível líquida de descontos, frete e estorno,
  ajuste de histórico/chargeback e verificação de custo/margem.
- Regras versionadas de ativação, metas, janela de elegibilidade,
  exclusão/cumulatividade, limite por cliente, orçamento sob lock.
- Recompensas não monetárias: pontos, vouchers, brindes,
  vantagens VIP, níveis, missões e indicações antifraude.
- Resgate demonstravelmente aplicado no checkout/PDV/Flow.
- LGPD e autorização do piloto, sistema de auditoria e rollback.

Nesta entrega nenhum webhook, wallet, loja real, token ou produção
é utilizado pelo motor.
