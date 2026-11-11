# Diferencial competitivo P0: cashback com controle de margem

Status: implementado como simulador sem persistência e sem ativação de descontos. A lógica financeira do backend é verificável e está isolada por tenant, mas a UI atual é uma demonstração local com valores digitados e dados fictícios.

## Nossa tese
Apps concorrentes já oferecem pontos, cashback, cupons e brindes. O Vidalys Fideliza precisa resolver um problema mais difícil: **qual é a recompensa máxima que o lojista pode oferecer sem romper sua margem mínima?**

O diferencial não é distribuir benefício; é recomendar limites financeiros responsáveis com transparência, bloqueios e relatórios, preservando rentabilidade.

## Primeira entrega em código
- Backend: POST autenticado em /api/v1/tenants/<uuid>/margin-simulations/ para usuários associados à loja. Não salva dados, não cria campanhas e não consulta Nuvemshop.
- Entrada: subtotal dos produtos antes dos descontos, descontos já existentes (Pix, cupons, etc.), custo das mercadorias (pode ser desconhecido), taxas de pagamento, subsídio de frete, outras despesas variáveis, taxa proposta de cashback e margem mínima.
- Saída: receita elegível líquida, crédito potencial, contribuição antes/depois, margem após incentivo, taxa máxima segura e orçamento máximo permitido.
- Custo desconhecido: sem taxa recomendada. Rejeitar valores inválidos, negativos ou descontos >= subtotal.
- Critérios: valores em centavos, taxas em bps (100 bps = 1%); arredondamento half-up para emissão e teto conservador para preservar margem. Retorno nunca concede recompensa automaticamente.
- UI: tela Rentabilidade, com cenários editáveis e diagnóstico de risco. A UI calcula localmente como demonstração e **não usa API autenticada** até existir login/tenant real.

## Fórmulas
- Receita elegível líquida = subtotal dos produtos - descontos existentes.
- Contribuição antes do incentivo = receita líquida - custo da mercadoria - taxa de pagamento - subsídio do frete - outras despesas variáveis.
- Crédito potencial = receita elegível líquida × percentual cashback (arredondado em centavos).
- Contribuição depois = contribuição antes - crédito potencial.
- Margem de contribuição = contribuição depois / receita elegível líquida.
- Reserva alvo de margem = ceil(receita líquida × margem mínima).
- Orçamento máximo de recompensa = min(receita líquida, max(0, contribuição antes - reserva alvo)).
- Taxa máxima recomendável = maior taxa em bps cujo crédito arredondado não supere orçamento.

## O que a simulação NÃO afirma
- Crédito emitido não representa necessariamente custo desembolsado, abatimento resgatado ou receita adicional.
- O custo do crédito é provisionado de modo conservador como 100% do benefício potencial.
- Itens sem custo conhecido exigem revisão. Custo nulo é dado declarado; custo não informado é NULL.
- Frete não deve entrar na base de cashback, mas seu subsídio entra no cálculo de contribuição.
- Impostos, embalagem e outros valores só entram se informados.
- Não mede uplift ou causalidade de campanhas; não calcula custo fiscal ou contábil definitivo.

## Próximas etapas (diferencial real a validar)
1. API de custos por SKU com fontes auditáveis e gestão de atualização por ERP; sem assumir que Nuvemshop possui custos completos.
2. Simulador por cesta mista/variante com regras de exclusão e faixas de cashback.
3. Controle de orçamento mensal de campanha, limites globais e proteção contra combos de Pix/cupom/frete.
4. Cohorts de recompra por grupo e comparação com holdout; não atribuir toda recompra ao cashback.
5. Alertas proativos de deterioração da margem e recomendação de benefícios alternativos (pontos, brindes de baixo custo).

## Testes de segurança e integridade
API não aceita anônimos ou outras lojas (retorna 404). Não há persistência. Backend e TS possuem casos de contrato equivalentes: margem, descontos existentes, custo desconhecido, emissão acima do limite e arredondamento. Frontend não acessa dados reais ou tokens.

## Qualidade P0
Manter a paleta Vidalys (grafite #0B1120, azul #1263FF, ciano #00D1E6). Validar screenshots reais em 390/768/1440 px, teclado e WCAG AA antes de considerar a interface aprovada; rótulos e disclaimers sempre visíveis. Não usar Django Admin como interface comercial.
