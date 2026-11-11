# Motor de fidelidade — regras de negócio v0.1

## Modalidades
- Cashback promocional: percentual do subtotal de produtos elegíveis, descontados os descontos efetivos, excluindo frete, juros e taxas. Crédito futuro, sem saque e sem transferências.
- Pontos: inteiros acumulados e convertidos em descontos ao atingir condição, com taxa explícita.
- Brindes físicos: fora do MVP; preservar futuras regras por SKU e local.

## Exemplo Bibelô para teste — NÃO ativo
**Escolher somente UMA modalidade inicialmente:** cashback de 2% ou 1 ponto/R$1, 100 pontos = R$2; mínimo R$5 para resgatar; compra mínima R$99; teto de resgate de 10% do subtotal líquido; validade de 90 dias após liberação. Ganho após pagamento, liberação sugerida após entrega + 7 dias. Pedidos sem entrega confiável necessitam política alternativa explícita. Não acumular com cupons inicialmente; testar combinabilidade Pix e frete grátis.

## Estados e lançamentos
Pedido criado (sem ganho) → pago (crédito `pending`) → condição de liberação (crédito `available`) → pedido elegível/resgate (`reserved`) → novo pedido pago (`redeemed`). Situações laterais: `expired`, `reversed`, `cancelled`. Cada mudança gera evento imutável no ledger, ligado a `(store_id, order_id, customer_id, rule_version, idempotency_key)`.

## Segurança econômica
Usar centavos inteiros + pontos inteiros, arredondar HALF_UP por pedido e não deixar saldo negativo. Valor do incentivo só é concedido em base de pagamento efetivo, após ajustes e elegibilidade. Custos dos produtos desconhecidos = alerta, NÃO custo zero. Proibir benefício acima do teto por pedido/campanha. Reservar saldo dentro de transação, com lock por carteira, expiração e confirmação por evento de pagamento. Não consumir saldo apenas ao visualizar checkout.

## Cenários imprescindíveis
- pagamento não confirmado = nada disponível;
- evento pago repetido 3 vezes = somente 1 crédito;
- compra R$200 em itens elegíveis → 2% = R$4;
- reembolso 30% = ajuste proporcional e registro de contralançamento;
- pedido cancelado ou chargeback = reversão / exceção auditável;
- duas requisições de resgate simultâneas não podem duplicar consumo;
- email igual em lojas diferentes não unifica carteira;
- cliente não autenticado não vê extrato;
- desconexão da loja revoga acesso e detém novas concessões;
- crédito vence mediante regra claramente comunicada.

## Fiscal e LGPD
Recompensa é crédito promocional futuro, não dinheiro sacável. Revisar legalidade de expiração e termos, base legal para comunicação, política de dados e tratamento fiscal no ERP/nota com contador e jurídico antes do piloto público.
