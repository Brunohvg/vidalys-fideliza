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


## Extensão G7 offline — conciliação de fatos normalizados (12/11/2026)

Código em backend/apps/nuvemshop/payment_reconciliation.py e testes em
test_payment_reconciliation.py. Função pura sem REST endpoint, token,
tarefa periódica, ORM ou escrita; aceita snapshot do leitor Nuvemshop
existente e eventos sintéticos normalizados de um FUTURO adaptador de PSP.

Critérios de segurança:
- Escopo obrigatório por tenant, loja, pedido, provedor, moeda BRL.
- Idempotência por provider + event_id. Reenvios idênticos não duplicam
  captura; evento com mesmo ID e conteúdo diferente é rejeitado.
- Duas capturas distintas do mesmo transaction_id são ambíguas e rejeitadas.
- Reembolso e chargeback precisam referenciar captura daquele provedor;
  a ordem de chegada não altera o cálculo (soma no fechamento).
- Bloqueia reembolso maior que capturas, valores negativos, floats/booleans,
  currency diferente, referências inválidas, eventos excessivos e
  transações de outra loja/pedido.
- Diagnósticos distintos para captura parcial, diferença com Nuvemshop,
  estorno parcial/chargeback, pagamento manual e cliente não verificado.
- Sem declarar aumento de conversão, economia, ROI, margem ou recompra.
  Não há valores de CMV/frete/taxas comprovados.
- Mesmo que os montantes batam, não existe prova autenticada do PSP
  até implementar o adaptador; o resultado nunca autoriza carteira,
  benefício, crédito ou resgate.

G7 continua PENDENTE EM PRODUCAO: autenticar contrato oficial
do PSP/ERP escolhido, distinguir captura, pagamento aprovado, liquidação,
cancelamento, chargeback e estorno parcial com identificadores e horários
do provedor, reconciliar contra a plataforma e vincular cliente que deu
consentimento. Depois validar margem por SKU, descontos cumulativos,
orçamento atomicamente e reversões antes de liberar benefício.

O motor financeiro OFF é explícito: payment_eligible_for_rewards=false,
independent_psp_proof_verified=false, credit_eligible=false,
cashback_created=false, ledger_writes_performed=0.
