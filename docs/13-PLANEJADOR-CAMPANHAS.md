# Planejador de campanhas — diferencial competitivo de orçamento

**Estado:** simulação financeira em PR #5, sem aplicação real de cashback, sem consulta a pedidos/Avanço e sem aprovação automática. Baseada no PR #4 de infraestrutura, que permanece independente do deploy em andamento pelo Work.

## Valor para o lojista
O lojista pode estimar **o orçamento que uma campanha de cashback exigiria** antes de distribuí-lo, sem confundir volume projetado com vendas reais. Além da margem mínima por pedido, há um limite mensal hipotético e uma quantidade de pedidos pagos informada.

Os cenários usam centavos inteiros e são calculados no servidor para usuários autenticados e associados ao tenant. Nenhuma simulação salva dados, reserva orçamento, instala script ou ativa desconto.

## Entradas
- Ticket elegível por pedido e descontos já existentes (Pix, cupons etc).
- Custo da mercadoria, que pode ser **desconhecido**, taxa de pagamento, subsídio do frete e outros custos.
- Percentual de cashback e margem mínima desejada.
- Pedidos pagos **projetados**, orçamento total mensal e créditos **já comprometidos** (dados informados pelo lojista, não importados).

## Indicadores
- Receita líquida elegível por pedido, crédito por pedido e exposição potencial (= crédito × pedidos projetados).
- Exposição total (= nova exposição + compromissos informados).
- Saldo orçamentário disponível (= máximo de zero e orçamento − compromissos).
- Pedidos suportados pelo saldo apenas em termos de crédito (= saldo / crédito por pedido, arredondado para baixo). Se crédito por pedido é zero: sem limite por crédito.
- Maior taxa matemática em pontos-base limitada pela margem e pelo orçamento; se faltar custo ou já houver excesso de compromissos, não mostrar taxa sugerida.
- Estados: dentro dos limites, risco de margem, orçamento insuficiente, orçamento já excedido, custo não informado e margem já insuficiente.

## Restrições de interpretação
- Não prever vendas, calcular causalidade ou prometer aumento de recompra.
- Custos faltantes são desconhecidos, nunca zero presumido.
- Nem toda exposição vira resgate. A simulação considera conservadoramente o benefício integral potencial, sem definir tratamento contábil.
- A tela autenticada mostra somente o resultado do cálculo daquele usuário/tenant; não consulta catálogo, pedidos ou receita real.
- Valores preenchidos de início são marcados como exemplos.
- Resultado positivo **não aprova** campanha. Dados reais, compliance e autorização continuam obrigatórios.
- Não aplicar uma única taxa a todas as SKUs sem conhecer custos e margens por cesta.

## Contrato da API
Endpoint: POST /api/v1/tenants/{uuid}/campaign-plans/preview/
Autenticação: sessão Django com CSRF; membership tenant obrigatório; tenant sem associação retorna 404.

Payload: mesmos campos da API de margem, mais:
- projected_paid_orders: 1..50.000.
- campaign_budget_cents: 0..1.000.000.000.
- already_committed_cents: 0..1.000.000.000 (default 0).

Retorna planning_only, status, somas em centavos, taxa máxima pelo orçamento e pela margem, teto conjunto e automatically_approved=false.

## Critérios visuais P0
- Tela com diagnóstico claro e configurações principais visíveis.
- Custos avançados ficam em seção expansível para reduzir complexidade inicial.
- Cenários predefinidos: orçamento apertado, limite ajustado e custo ausente.
- Valores fictícios rotulados, feedback de carregamento/erro/vazio e acessibilidade.
- Testes Playwright em 390/768/1440px e isolamento da API.

## Próximo ciclo
Controle persistente de campanhas, versionamento de regras e orçamento por SKU, depois ledger e emissão/resgate, somente após validação de OAuth/Discount API Nuvemshop. No momento a funcionalidade é somente leitura e não afeta a homologação em implantação.
