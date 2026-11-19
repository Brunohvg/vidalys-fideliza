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
- Falha ao criar na Nuvemshop → reserva devolvida, cupom "falhou", nova tentativa na próxima hora.
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
5. Serviços `beat` e `nuvemshop-sync` rodando. Migração `sales.0012_online_redemption`.

## Limites conhecidos / próxima fase
- Pedido cancelado **depois** de usar o cupom: o resgate não é desfeito automaticamente.
- Fase 2: aplicar o saldo sozinho no carrinho via API de Descontos (sem digitar código).
