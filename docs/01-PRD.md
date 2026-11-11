# Vidalys Fideliza — PRD (proposta v0.1)

**Status:** especificação inicial, ainda não aprovada e não implementada. 10/11/2026.

## Produto
Aplicação SaaS independente do Vidalys Flow, para Nuvemshop primeiro, com programa de fidelidade, cashback promocional, pontos, recompra e controle de custo. Integração com Flow para comunicação é opcional e posterior. Nome e logo de trabalho até verificação no INPI e disponibilidade comercial.

## Segmento e hipótese
Gestores de lojas com ~50–1000 pedidos/mês que precisam melhorar recompra e conhecer margem real, sem equipe técnica. Compradores desejam benefício previsível, sem surpresas no checkout. Teste em Bibelô antes de oferta pública.

## Evidência Bibelô
Janela 11/10–09/11/2026 por data de **pagamento**: 127 clientes novos, 149 recorrentes, R$20.903,16 novos, R$31.924,41 recorrentes. Recorrentes representam ~60% do valor; não prova causalidade nem margem.

## Problemas a resolver
1. Compra única e baixa previsibilidade da recompra.
2. Promoções sem medir custo real e concorrência com desconto Pix, cupom e frete grátis.
3. Estornos, saldo e expiração sem reconciliação segura.
4. Pouca clareza para cliente sobre validade e desconto elegível.

## Escopo MVP
OAuth da Nuvemshop; multi-loja; modalidade de pontos **ou** cashback por programa; pendência, liberação, reserva, resgate e estorno; carteira do cliente; regras de elegibilidade, limite e validade; painel simples de ROI/retorno; webhooks idempotentes; auditoria; desinstalação; onboarding e suporte mínimo.

## Fora do MVP
Indicação, níveis VIP, brinde físico, NPS, gamificação, WhatsApp obrigatório, saques Pix, conciliação fiscal Avanço, IA preditiva, multicanal fora da Nuvemshop.

## Critérios de sucesso / stop-go
POC comprova resgate real no checkout da loja. Política fiscal e margem validada por contabilista. Piloto 60–90 dias com controle/holdout quando viável. Medir taxa de segunda compra, custo de crédito emitido/usado, ticket líquido, margem após incentivo e reclamações. Depois entrevistar 5–10 lojistas sobre vontade de pagar. Se resgate não for seguro, reduzir MVP a emissão transparente de cupons pós-compra.

## Estado da decisão
Arquitetura independente do Flow é recomendação; marca, modalidade, 2%, validade, precificação e plano de distribuição seguem **propostos**.


## Requisito P0 — Design premium verificável
UX/UI tem mesma prioridade que segurança e integridade financeira. Protótipos de alta fidelidade, revisão de marca, responsividade real (390/768/1440px), WCAG AA e screenshots de referência são obrigatórios antes de aceitar interfaces comerciais. Ver `docs/08-UX-UI-CRITERIOS.md`.
