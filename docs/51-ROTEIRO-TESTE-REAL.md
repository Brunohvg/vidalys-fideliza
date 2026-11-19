# 51 — Roteiro do teste real (itens 6 e 7 do docs/50)

Feito pelo operador, na loja de demonstração (modo **teste**: no máximo R$ 50 por compra).
Marque cada passo e anote a evidência (print ou saída do comando). CI verde não substitui isto.

## Parte A — Deploy conferido (item 7)

| # | Passo | Esperado | ✔ |
|---|---|---|---|
| A1 | Coolify → api → Terminal: `python manage.py club_readiness` | "Banco com todas as migrações aplicadas", Redis respondendo, worker da fila nuvemshop, "Resultado: OK" | ☐ |
| A2 | Mesma saída: "Versão implantada" | Igual ao último commit da branch no GitHub (se aparecer "não informada", conferir no Coolify → Deployments) | ☐ |
| A3 | Serviços `api`, `frontend`, `worker`, `beat`, `nuvemshop-sync`, `redis` | Todos "Running" e saudáveis no Coolify | ☐ |
| A4 | Abrir o painel e o Meu Clube público da loja | Carregam sem erro; Meu clube mostra "Modo teste" | ☐ |
| A5 | `python manage.py nuvemshop_webhooks --tenant <slug> --ensure` (lojas conectadas antes do cadastro automático) | "✔ order/paid" e "✔ order/updated"; `club_readiness` passa a mostrar os dois avisos cadastrados | ☐ |

Se A1 mostrar migração pendente: backup → `FIDELIZA_APPLY_MIGRATIONS=1` → Redeploy → voltar para 0 → repetir A1.

## Parte B — Balcão

| # | Passo | Esperado | ✔ |
|---|---|---|---|
| B1 | Vendas → Balcão: venda de R$ 100 com o celular de uma cliente de teste | Venda em "Conferir" | ☐ |
| B2 | Conferir → Confirmar | Saldo pendente gerado (giftback 10% = R$ 10, respeitando teto) | ☐ |
| B3 | Desfazer uma venda recém-registrada (até 5 min) | Some de Conferir, sem saldo | ☐ |
| B4 | Depois da carência (ou carência 0), nova venda ≥ compra mínima usando o crédito | Desconto aplicado; Meu Clube mostra "Crédito usado na loja" | ☐ |

## Parte C — Site (Nuvemshop)

| # | Passo | Esperado | ✔ |
|---|---|---|---|
| C1 | Com o e-mail confirmado da cliente de teste, fazer um pedido pago no site | Em até alguns minutos: `club_readiness --tenant <slug>` mostra +1 aviso de pedido e +1 "compra do site que gerou saldo" | ☐ |
| C2 | Saldo liberado → Meu Clube da cliente → **Gerar cupom** | Aparece o cupom com código; Nuvemshop → Descontos mostra o mesmo código, uso 1, compra mínima e validade | ☐ |
| C3 | Novo pedido usando o cupom (botão "Comprar com o cupom") | Desconto no carrinho; depois de pago, cupom "usado" e saldo baixado | ☐ |
| C4 | Cancelar/reembolsar o pedido do C3 na Nuvemshop | Ganho do pedido sai; crédito usado volta uma vez ("Crédito de volta: pedido cancelado") | ☐ |
| C5 | Gerar cupom e, antes de usar no site, usar o crédito no balcão | Cupom do site some na Nuvemshop; crédito usado no caixa | ☐ |
| C6 | Tentar usar o mesmo código de novo no site | Nuvemshop recusa (uso 1) | ☐ |

## Parte D — Situações adversas que dá para provocar

| # | Passo | Esperado | ✔ |
|---|---|---|---|
| D1 | Pausar o clube e fazer pedido pago com cupom já gerado | Cupom baixado como usado; o pedido não gera saldo novo | ☐ |
| D2 | Teto por venda acima de R$ 50 no painel | Recusado: "No modo teste, o teto por venda vai até R$ 50,00" | ☐ |
| D3 | Abrir o Meu Clube de outra loja logado como a cliente de teste | Não aparece saldo/cupom da primeira loja | ☐ |
| D4 | Desligar `FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED` e tentar gerar cupom | "Resgate pelo site está desligado nesta loja"; saldo intacto | ☐ |

## O que este roteiro NÃO cobre (testado só com simulação no CI)
Resposta HTTP perdida na criação do cupom, worker morto no meio da operação e duas requisições
simultâneas. Esses casos têm testes automatizados (`test_online_redemption.py`).

## Fechamento
Com A1–A4, B1–B4 e C1–C6 marcados e evidências guardadas, os itens 6 e 7 do docs/50 ficam
"Feito". Só então liberar o modo comercial de uma loja com `set_store_operation`.
