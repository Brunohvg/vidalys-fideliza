# 40 — Inbox de webhooks de pedido (somente homologação)

## Situação
A branch homolog possui uma recepção **opcional e desativada por padrão** de notificações Nuvemshop de pedidos. Este marco permite confirmar que eventos assinados chegam ao sistema e são armazenados de modo idempotente. **Não confirma pagamento, não cria crédito e não altera pedidos.**

## Contrato
- Endpoint HTTPS: POST /api/v1/webhooks/orders/paid/ para order/paid; POST /api/v1/webhooks/orders/updated/ para order/updated.
- Somente application/json, corpo de até 64 KiB e assinatura HMAC-SHA256 no header x-linkedstore-hmac-sha256 sobre os bytes brutos do corpo. Chave: NUVEMSHOP_CLIENT_SECRET do aplicativo parceiro, nunca access_token da loja.
- Campos obrigatórios no JSON: store_id positivo, id positivo do pedido, event correspondente à rota e event_launch_ts Unix em segundos. JSON malformado, assinatura inválida ou divergência de evento não é aceito.
- A API procura um tenant Nuvemshop ativo com external_store_id correspondente, instalação da mesma aplicação e scope read_orders/write_orders. Instalações de outra loja, outro app ou suspensas não geram registros locais.
- Em sucesso: 202 com { "received": true } somente **depois** da transação. Falha do banco: HTTP 503 para provocar reentrega.
- Recebimento duplicado do mesmo app+loja+evento+pedido+timestamp não gera outra linha, mesmo quando o corpo recebe atributos adicionais. Eventos posteriores com outro timestamp geram outra linha. Eventos distintos no mesmo segundo são coalescidos deliberadamente: essa inbox é um gatilho de releitura, não um histórico financeiro.
- O banco mantém apenas tenant_id, store_id, order_id, topic, event_launch_ts, dedupe_key e received_at; nunca persiste o JSON, nome, e-mail, endereço, token ou assinatura. Nenhum dado financeiro é contabilizado.
- Endpoint interno de conferência: GET /api/v1/tenants/<tenant_uuid>/nuvemshop/orders/events/ (proprietário ou administrador), com últimos 20 avisos e marcador pending_reconciliation. Retorna dados mínimos, sem PII.
- FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=0 permanece desligado até teste completo, HTTPS válido, OAuth da loja piloto e registro autorizado das duas assinaturas de eventos no app. Somente o container API recebe a flag e os segredos do parceiro; worker e frontend não recebem credenciais.
- FIDELIZA_LEDGER_WRITES_ENABLED permanece **False em código**. Não há reconciliação real nem gravação de saldos, extratos, resgates, automações ou ações Nuvemshop.

## Diferenças relevantes
- order/paid pode ser pago via gateway ou **marcado manualmente como pago**. Não interpretar como liquidação.
- order/updated inclui eventos de estorno, chargeback, edições e diversas mudanças de status. Pode chegar junto de order/paid para a mesma alteração.
- A Nuvemshop não promete ordem de chegada nem unicidade: não conferir saldo com base na última notificação recebida.
- O próximo marco é consumir a inbox para reler estado atual pela API 2025-03, checar identidade consentida, conciliar pagamentos/estornos e fechar um contrato de idempotência contábil **antes de habilitar qualquer ledger**.
- Dados pessoais e comandos LGPD continuam sob as rotas específicas já existentes, sem mudança no processamento de privacidade.

## Teste de homologação — sequência
1. Verificar CI, migração 0005, isolamento de variáveis e execução offline dos testes sintéticos.
2. Autorizar explicitamente read_orders na loja de teste, manter secrets exclusivamente no backend API e habilitar a flag somente no recurso piloto.
3. Registrar HTTPS para os dois eventos no portal/API da Nuvemshop, evitando duplicação de assinaturas já instaladas.
4. Enviar um pedido fictício na loja piloto, conferir recebimento de order/paid e order/updated e verificar que reenvios não duplicam evento.
5. Consultar o novo endpoint administrativo e comparar GET de pedido com o status real do gateway. Conferir que nenhuma carteira recebeu crédito.
6. Desligar a flag caso haja divergência; nunca liberar saldo com base apenas neste teste.

Documentação oficial: https://nuvemshop.dev/docs-api/resources/2025-03/webhook
