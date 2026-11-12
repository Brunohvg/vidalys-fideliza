# 41 — Inspeção de evento recebido (read-only)

O webhook indica uma mudança de pedido. A API consulta de novo seu estado
atual na Nuvemshop, sem presumir que o evento prova pagamento.

GET /api/v1/tenants/{tenant_id}/nuvemshop/orders/events/{event_id}/inspect/

- Administração do próprio tenant; scopes read_orders, instalação OAuth,
  flags da inbox e prévia de pedidos exigidas.
- Usa o pedido registrado pelo webhook assinado; não aceita ID arbitrário.
- Reutiliza GET oficial, rate-limit, verificação de participante e bloqueio
  de pagamento manual, cancelamentos e estornos.
- Não guarda PII, nenhum histórico adicional e nenhum saldo; sempre indica
  credit_eligible false e requires_psp_reconciliation true.
- Uma leitura da API não é prova independente de liquidação do PSP.
- Não libera nada em produção, não altera main nem deploy Coolify.

Pendente antes da concessão financeira: reconciliação de valor líquido,
cancelamentos e estornos, identidade e consentimento, regra versionada,
orçamento, idempotência contábil, auditoria, aprovação do piloto e resgate.
