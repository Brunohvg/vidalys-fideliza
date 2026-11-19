# 47 — Ganhar e resgatar no site (Nuvemshop)

Vale para **qualquer loja** conectada. Cada loja liga, pausa e configura o seu em
Meu clube → 1. Como ganhar → cartão "No balcão" → seção **No site (Nuvemshop)**.

## Referência de mercado (nov/2026)
- CRM&Bônus: cada compra gera **um cupom da cliente**; bônus visíveis no carrinho; lembretes.
- BonifiQ: troca de pontos em widget com **cupom gerado automaticamente**.
- Práticas comuns: validade ~30 dias, liberação alguns dias após a compra, uso único e
  intransferível, regra de acúmulo com outras promoções, pausa em datas como Black Friday.
- API de cupons da Nuvemshop (`/coupons`): `code`, `type`, `value`, `max_uses`, `min_price`,
  `start/end_date`, `combines_with_other_discounts`… **não restringe por cliente**. Por isso o
  padrão é código único e difícil de adivinhar por saldo, com `max_uses = 1`.
- Link que já aplica o cupom: `https://<loja>/discount/<CODIGO>`.

## Como funciona
**Ganhar no site** — webhook de pedido → reconsulta OAuth (`nuvemshop.recheck_order`) →
`apps.sales.online.handle_order`:
- pedido **pago** de cliente do clube (perfil verificado ou e-mail confirmado no clube, um único
  cadastro) gera lote pendente `site:<pedido>` pela regra do modo (pontos ou giftback), com teto
  por venda e orçamento total; idempotente para webhooks repetidos;
- **cancelado/estornado**: o que ainda não foi usado do lote é estornado.

**Resgatar por cupom único** — `OnlineCoupon`:
- **Giftback**: quando o crédito libera, a rotina horária (`sales.online_coupon_refresh`, fila
  `nuvemshop`, minuto 15) cria um cupom com **todo o crédito**: valor absoluto, uso 1, compra
  mínima do giftback, validade do crédito. Crédito novo liberou → o cupom antigo é apagado e um
  novo é criado com o total (sempre um cupom por cliente). A cliente também pode gerar na hora
  pelo Meu Clube.
- **Pontos**: a cliente escolhe a recompensa no Meu Clube → **Cupom para o site** (30 dias).
- O saldo fica **reservado** no ledger enquanto o cupom existe.
- Pedido pago com o código → resgate (`REDEEM`), cupom "usado".
- Uso no **caixa** → o cupom do site é apagado na Nuvemshop e o crédito volta para ser usado ali.
- Vencido → apagado e reserva devolvida.
- Resultado incerto ao criar (timeout, resposta perdida, worker reiniciado) → cupom **Confirmando**:
  a reserva **continua**, o código não aparece para a cliente e o caixa não consegue liberar o saldo.
  A rotina horária confere pelo código exato na Nuvemshop (`reconcile_coupon`):
  existe → disponível; a Nuvemshop confirma que não existe **e** já passaram 10 min → falhou e a
  reserva volta; resposta inconclusiva → continua Confirmando (nunca libera por dúvida).
- Pedido pago com o código de um cupom em Confirmando → resgate normal. Com o código de um cupom já
  liberado (corrida com o caixa) → o saldo ainda disponível é debitado e a falta fica na auditoria.
- Clique duplo / duas abas: devolve o mesmo cupom, sem segunda reserva.
- Cada cupom guarda uma trilha curta (`audit`): reservado, criação incerta, conferido, usado, cancelado.
- O e-mail "seu crédito liberou" inclui o código e o botão "Comprar com meu cupom".

**Opções do lojista**: ganhar no site, resgate por cupom, somar com outras promoções (padrão
desligado), pausar novos cupons (cupons já gerados continuam valendo).

## Requisitos (aparecem como checklist no painel)
1. Loja Nuvemshop conectada.
2. `FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=1`, `..._ORDER_WEBHOOKS_ENABLED=1`,
   `..._ORDER_RECHECK_ENABLED=1` (API e worker `nuvemshop-sync`).
3. Permissão **Cupons** (`write_coupons`) habilitada no app do Portal de Parceiros e a loja
   reautorizada (Configurações → Canais → Atualizar conexão).
4. `FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=1` (API e `nuvemshop-sync`).
5. Serviços `beat` e `nuvemshop-sync` rodando. Migrações `sales.0012_online_redemption` e `sales.0013_coupon_uncertain`.

## Limites conhecidos / próxima fase
- **Titularidade**: a API de cupons da Nuvemshop não vincula cupom a cliente. Quem tiver o código
  consegue usar uma vez. Mitigação: código aleatório de 8 caracteres, uso 1, compra mínima e validade.
- Pedido cancelado/reembolsado **depois** de usar o cupom: o ganho do pedido é estornado e o
  crédito usado volta para a cliente uma única vez (lote `site-refund:<cupom>`, regra `pilot-vr1`,
  validade original com mínimo de 7 dias). Não conta como compra nem gasta orçamento. Cliente que
  saiu do clube: não volta (fica `restore_skipped` na auditoria). O cupom antigo não volta a valer.
- Fase 2: aplicar o saldo sozinho no carrinho via API de Descontos (sem digitar código).
