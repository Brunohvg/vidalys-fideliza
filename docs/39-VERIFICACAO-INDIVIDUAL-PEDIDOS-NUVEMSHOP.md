# Homologação: consulta individual de pedidos, sem cashback

Data: 11/11/2026 (America/Sao_Paulo). Branch homolog.
Status: código preparado, não prova publicação no Coolify nem consulta à Bibelô.

## Entrega funcional

GET /api/v1/tenants/{tenant_uuid}/nuvemshop/orders/{order_id}/preview/

- Requer autenticação e papel owner/admin da própria loja, flag
  FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED ligada no serviço API
  e read_orders concedido no token efetivo dessa instalação.
- Usa exclusivamente store_id e token cifrado do backend, sem aceitar
  store_id, access_token ou URL externos pelo navegador.
- Verifica pela Admin API estável 2025-03 o estado atualizado de um
  único pedido: status, payment_status, paid_at, total, moeda e gateway.
- Quando read_customers também está autorizado e a flag de consulta
  de clientes estiver ligada, considera correspondência apenas por
  customer.id com participante ativo da mesma loja.
- Retorna somente fatos mínimos para operação, sem contato, endereço,
  produtos, token ou corpo bruto do pedido.
- Não concede saldo, não salva pedidos, não cria CashbackEvent e não
  altera nada na Nuvemshop.

## Limite do significado de pago

O webhook order/paid também pode ser provocado pelo administrador
marcando o pedido como pago. Gateway internal/offline requer revisão
explícita. Um pagamento com gateway comum ainda exige conciliação
antes de qualquer concessão. Reembolsos e cancelamentos bloqueiam
o avanço; pedido parcialmente pago não é pago.

O total exibido é valor reportado do pedido, não receita líquida,
valor liquidado ou base de cashback. A documentação oficial orienta
usar GET /orders/{id}/history/values e, quando necessário, registros
do provedor para reembolsos e chargebacks.

Fontes:
https://nuvemshop.dev/docs-api/resources/2025-03/order
https://nuvemshop.dev/docs-api/resources/2025-03/webhook
https://nuvemshop.dev/api/getting-started

## Gate de ativação

Por padrão FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=0.
Ela só pode ser ligada na API da Application correta de homologação
após backup, conferência do commit, instalação/reautorização OAuth em
LOJA DE TESTES com read_orders, e teste da API com pedido sintético.
Nunca copiar tokens para frontend, worker, Redis, logs ou Notion.
Mesmo com a flag ligada, o ledger e o resgate real continuam OFF.

## Próximo desenvolvimento

Receptor de eventos order/paid e order/updated com assinatura HMAC
do corpo original, inbox de eventos idempotente, processamento
assíncrono e reconciliação de pagamento, reembolso e cancelamento.
Depois, modelo de compra verificada, concessão pendente controlada,
liberação, estorno e resgate. Não inferir cobrança liquidada somente
pelo webhook order/paid.
