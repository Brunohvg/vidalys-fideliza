# 50 — Plano para abertura comercial (único plano de execução)

Base: `feature/diferenciais-clube` (PR #33). A homolog é só referência histórica.
Testes controlados continuam livres; cada item abaixo é **obrigatório antes de vender**.

| # | Item | Risco | Status | Evidência |
|---|---|---|---|---|
| 1 | Cupom do site com resultado incerto não libera saldo | Crédito usado duas vezes | **Feito** | `sales.0013`, `reconcile_coupon`, 10 testes em `test_online_redemption.py`, e2e "confirmando" |
| 2 | Política central Teste x Comercial por loja (substitui `pilot_allowed()` e a exceção em `points/services.py`) | Motor financeiro ligado sem controles | **Feito** | `apps/sales/policy.py`, `sales.0014`, comando `set_store_operation`, 7 testes em `test_operation_policy.py`, e2e do aviso no painel |
| 3 | Limites financeiros em R$: teto por venda, orçamento, limite menor no modo Teste | Erro de digitação vira prejuízo (antes até R$ 1.000/venda e R$ 100.000) | **Feito** | Teste: R$ 50/compra e R$ 2.000 no total. Comercial: R$ 200 e R$ 10.000. Aplicado na hora, mesmo para tetos já salvos |
| 4 | Balcão: papel Vendedor (registra, não confere) e gerente sem autoconferir venda alta | Funcionário concede saldo a si mesmo | **Depende de convites de equipe** | Hoje não existe convite ("Convites em breve"): só o proprietário confere. Fazer junto com Equipe |
| 5 | Pedido cancelado/estornado depois de usar cupom | Cliente perde o crédito ou ganho indevido continua | **Feito** | Ganho do pedido estornado; crédito usado volta uma vez (`site-refund:`), sem gastar orçamento; 2 testes |
| 6 | Teste real ponta a ponta numa loja Nuvemshop (OAuth → pedido pago → cupom → uso → reembolso) | CI usa mocks | Pendente (operador) | Roteiro: docs/51, partes B, C e D |
| 7 | Deploy conferido: commit implantado, migrações aplicadas, API/beat/nuvemshop-sync saudáveis | Versão defasada | Pendente (operador) | `python manage.py club_readiness` (docs/51, parte A) |

## Revisão do parecer externo (19/11/2026)
| # | Ponto | Status | O que foi feito |
|---|---|---|---|
| 8 | Falha do clube escondida com o pedido marcado `checked` | **Feito** | Clube roda logo após conferir loja/pedido, antes das paradas por identidade do motor antigo; falha grava `club_retry` e a tarefa repete; `club_readiness` mostra ✖ |
| 9 | Cupom incerto liberado após uma consulta negativa e 10 min | **Feito** | Libera só com cupom de 1 h+ e duas consultas negativas com 30 min de intervalo; se o código aparecer num pedido depois, o uso tardio debita |
| 10 | "Pago" na Nuvemshop não é liquidação comprovada | **Garantia definida** | Comercial exige carência de 7+ dias no site; reconsulta OAuth; estorno automático em cancelado/reembolsado/anulado. Risco restante: chargeback depois da carência, limitado ao teto por compra (R$ 200) |
| 11 | Concorrência real com PostgreSQL e worker caindo | Pendente | Coberto por testes com simulação; falta teste com PostgreSQL e operações simultâneas |
| 12 | Documentação legada contraditória | Pendente | docs/52 corrigido; consolidar 38–49 num guia único depois do teste real |

## Política de operação (item 2)
- **Teste** (padrão de toda loja): tudo funciona, com tetos fixos baixos. Não precisa liberar nada.
- **Comercial**: só pelo comando, rodado por superusuário no serviço `api` do Coolify:
  `python manage.py set_store_operation --tenant <slug> --mode commercial --actor <superusuario> --confirm COMMERCIAL`
  Recusa se faltar requisito. Voltar: `--mode test --confirm TEST` (sempre aceito).
- Requisitos do comercial, conferidos a cada operação (caiu → bloqueia o canal na hora):
  regulamento e privacidade publicados; regra salva; liberação registrada; no site, pedidos pagos,
  cancelados e reembolsados chegando e reconsultados; cupons liberados; nenhum cupom sem
  confirmação há mais de 24 h (este só bloqueia novos cupons).
- Baixas (resgate, estorno, vencimento, devolução de reserva) acontecem mesmo com o clube pausado:
  pausar não deixa cupom usado sem baixa. Crédito novo, liberação e reserva exigem poder operar.
- A flag global `FIDELIZA_POINTS_WRITES_ENABLED` não fura a política em loja com clube; ela só vale
  para o motor antigo, em lojas sem clube.

## O que é testado onde
- **Mocks (CI)**: regras do ledger, cupom incerto, conferência, corrida caixa x site, webhook repetido.
- **Navegador local (Playwright, API simulada)**: telas e estados (inclusive "confirmando").
- **Integração real**: só nos itens 6 e 7, feitos pelo operador com a loja piloto.
