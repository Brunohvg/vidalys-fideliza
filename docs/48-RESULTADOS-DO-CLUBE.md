# 48 — Resultados do clube

Tela **Resultados** ("O que o clube trouxe"), por loja, só com registros reais do Fideliza.
API: `GET /api/v1/tenants/<id>/loyalty/results/?days=30|90` → `apps.sales.results.club_results`.

## O que mostra
| Bloco | De onde vem |
|---|---|
| Vendas do clube | lotes do clube criados no período (`pilot-v*`): compra conferida no balcão ou pedido pago no site |
| Clientes que voltaram | compradoras do período com compra anterior **ou** 2+ compras no período |
| Desconto concedido + custo real | resgates no balcão (`CounterRedemption` resgatado) + cupons do site usados; custo = desconto ÷ vendas do clube |
| Saldo/crédito com as clientes | disponível + reservado dos lotes vigentes; "a liberar" = pendente |
| Gerado x usado por mês | soma emitida e eventos `REDEEM`, últimos 6 meses |
| Para onde foi o saldo | do que foi gerado no período: usado, ainda em aberto, vencido, estornado |
| Venda que o desconto puxou | valor das compras em que a cliente usou vale/crédito |
| Balcão: clube x fora | vendas de balcão registradas (exceto rejeitadas), com e sem participante |
| Novos membros por mês | data de adesão dos participantes |

Giftback mostra tudo em R$; pontos mostra pts (1 pt = R$ 0,01 de desconto) e R$ nos valores de venda.

## Regras
- Sem grupo de comparação: a tela **não** afirma que o clube causou vendas (`causal_claim: false`
  e aviso fixo no rodapé). Comparação clube x fora é descritiva.
- Multi-loja: tudo filtrado por `tenant`; nada de dados de outra loja.
- Gráficos: paleta categórica validada, legenda, dica no hover/foco e tabela para leitor de tela.
