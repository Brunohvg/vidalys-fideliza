# 46 — Etapa preliminar G7: divergência financeira, sem crédito

Documento oficial da Nuvemshop Admin API 2025-03:
https://nuvemshop.dev/docs-api/resources/2025-03/order

O GET restrito de pedido agora solicita 'total_paid_by_customer' e
compara ao campo 'total' do mesmo pedido, ambos em centavos decimais.
O objetivo é apontar divergências relevantes antes de conciliar PSP/ERP,
não comprovar pagamento.

- Valor pago ausente: não inferir zero nem afirmar que houve liquidação.
- Valor informado diferente: 'reported_paid_amount_review'.
- Cancelamento ou reembolso tem prioridade sobre essa divergência.
- Pagamento manual continua em 'manual_payment_review'.
- Quando igual e demais critérios locais batem, status continua
  'reported_paid_requires_reconciliation'; nunca 'verified_paid'.
- O JSON não inclui dados pessoais nem credenciais. Rejeita valores
  negativos, NaN, montantes com frações de centavo e estrutura inválida.
- Nada é persistido: a prévia e a reinspeção da inbox são somente GET.
- credit_eligible=false, cashback_created=false e
  FIDELIZA_LEDGER_WRITES_ENABLED=False permanecem forçados.

Aviso explícito da documentação da Nuvemshop: 'total_paid_by_customer'
não precisa coincidir com 'total' por pagamento parcial, edição e
transação sem correspondência. Diferença é alerta, não culpa/fraude
nem perda comprovada. Não aplicar tolerância ou fórmula por aproximação
sem conciliação do meio de pagamento e política comercial.

G7 PENDENTE: recuperar fatos de transação por adaptador autenticado
ao provedor de pagamento/ERP, validar captura, devolução parcial,
reembolso total, chargeback, referências, timestamp, valor líquido,
moeda e idempotência de operação. Só depois criar registros
financeiros verificados e submeter concessão ao motor de regras.
Homologação deve usar compras/pagamentos sintéticos primeiro.
Nenhuma loja real foi consultada nem houve deploy.
