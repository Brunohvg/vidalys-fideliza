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
| 8 | Falha do clube escondida com o pedido marcado `checked` | **Feito** | Falha grava `club_retry` e a tarefa repete; esgotadas as tentativas, a rotina horária devolve o pedido à fila (sem limite de dias); `club_readiness` mostra ✖ |
| 8a | Baixa e concessão misturadas (concederia antes da titularidade / com contato contraditório) | **Feito** | Etapa 1 (logo após conferir loja/pedido): só baixas — cupom usado, estorno, devolução. Etapa 2 (depois de identidade coerente e titularidade): concessão. Contato contraditório ou violação param antes da etapa 2 |
| 9 | Cupom incerto liberado após uma consulta negativa e 10 min | **Feito, com risco residual** | Libera só com cupom de 1 h+ e duas consultas negativas com 30 min de intervalo. A busca da Nuvemshop por código pode ser incompleta: se o cupom existir e for usado depois, o uso tardio debita o saldo que houver e registra a falta |
| 10 | "Pago" na Nuvemshop não é liquidação comprovada | **Proteção de risco (não é prova)** | Comercial exige carência de 7+ dias no site; reconsulta OAuth; estorno automático em cancelado/reembolsado/anulado. Contestação depois da carência continua possível, limitada ao teto por compra (R$ 200) |
| 11 | Concorrência real com PostgreSQL e worker caindo | **Feito (CI)** | `test_concurrency_postgres.py`: duas conexões ao mesmo tempo gerando cupom, processando o mesmo pedido pago e gastando o mesmo saldo; testes do clube também rodam em PostgreSQL no job `external_database_smoke`. Corrigido: pedido duplicado simultâneo não tenta criar o lote duas vezes |
| 11a | **Bug real achado pelo PostgreSQL do CI**: Confirmar venda (Conferir, individual e em lote) dava erro 500 em PostgreSQL (`FOR UPDATE cannot be applied to the nullable side of an outer join`) | **Feito** | Lock só na linha da venda (`select_for_update(of=("self",))`). No SQLite o erro não aparece, por isso o CI comum passava |
| 11b | **Achado no teste real**: pedidos de clientes paravam em "Contato informado exige conferência manual" (motor antigo recusa telefone sem +55 e contato fora do cadastro verificado) antes de o clube conceder | **Feito** | Clube concede com regra própria logo após a titularidade: e-mail confirmado no clube; celular brasileiro válido e diferente do cadastrado desmente e bloqueia; celular ilegível não bloqueia. Pedidos parados agora aparecem no `club_readiness` como conferência manual |
| 13 | Cadastros com e-mail confirmado parados em "aguardando a loja" (pendências manuais) | **Feito** | Loja com clube: e-mail confirmado = participação ativa, sem aprovação; vínculo Nuvemshop vira complemento. `activate_verified_members` corrige os parados |
| 14 | Compra no site com outro e-mail não contava; compras feitas antes da ativação ficavam sem crédito | **Feito** | Cliente da Nuvemshop lembrado na 1ª compra reconhecida; crédito retroativo automático dos pedidos pagos depois da adesão (até 30 dias), sem duplicar |
| 15 | Apagar cliente e venda de balcão | **Feito** | Remover cliente: cupom do site cancelado, saldo zerado no ledger, dados pessoais apagados ("Cliente removido"). Apagar venda: motivo obrigatório, saldo gerado estornado, crédito usado volta, número do cupom liberado, some de listas e resultados |
| 16 | Cadastro manual de cliente | **Feito** | Nome, e-mail, celular e autorização declarada; participação ativa na hora; site conta depois que a cliente confirma o e-mail |
| 17 | Auditoria do commit 70f94aa: anular venda cujo saldo já foi gasto | **Feito** | "Apagar" virou **Anular venda**. Crédito pendente/disponível é estornado; o que a cliente já gastou é descontado do saldo dela; sem saldo para cobrir, a anulação é **recusada** e nada muda. Venda com crédito reservado no caixa também é recusada até a reserva sair |
| 18 | Crédito retroativo por caminho próprio | **Feito** | Agora só **encontra** os pedidos dela (busca na Nuvemshop pelo e-mail confirmado, em lotes de 50) e passa cada um pela **mesma reconsulta** dos pedidos normais (loja, status, titularidade, regra do clube). Falha vira `club_retry` e é retentada de hora em hora. Pedido pago antes da adesão nunca gera crédito |
| 19 | Remoção de cliente vs. dados pessoais | **Feito** | Vínculo com o cliente da Nuvemshop também é anonimizado; registro auditável `ParticipantRemoval` com motivo, quem fez, quanto estornou, cupons cancelados e resultado dos dados (`erased` ou `retained` quando um registro protegido precisa ficar). A tela não promete apagar o que ficou retido |
| 20 | Resultados contavam desconto de venda anulada | **Feito** | Venda anulada sai também dos descontos usados. O **orçamento** do teste continua contando o que já foi emitido (exposição histórica), de propósito: anular não devolve teto |
| 21 | Confirmação de e-mail de cliente cadastrada pela loja | **Feito** | Cadastro pela loja = participação ativa; site só concede depois do e-mail confirmado. Confirmar o e-mail depois responde "participação existente — e-mail confirmado" |
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
