# 51 — Resgate de pontos na Nuvemshop: contrato do MVP

**Data:** 13/11/2026. **Decisão aprovada:** desconto fixo na próxima compra,
com resgate pelo site e o máximo de automação seguro possível.
**Estado:** proposta técnica para o motor de resgate; **não implementado no checkout**.
**Loja real:** nenhuma criação ou edição de cupom, alteração de tema ou nova
permissão OAuth autorizada por este documento.

## Por que este módulo faz parte do MVP

O Fideliza mantém cadastro, consentimento e carteira próprios. A Nuvemshop
é apenas o primeiro canal de comércio eletrônico que recebe e aplica
benefícios. Sem resgate real no site, a carteira não fecha a jornada.

Jornada prevista:

1. Consumidor verifica o acesso ao **Meu Clube** sem usar credenciais do lojista.
2. A API apresenta **somente recompensas publicadas**, aplicáveis ao canal
   da loja e com valor de desconto, custo em pontos, condições, prazo e
   status (disponível, faltam pontos, suspensa, indisponível).
3. A ação de resgatar revalida identidade do participante, consentimento,
   wallet, vínculo da loja, recompensa publicada, saldo, limites e prazo.
4. Reserva pontos atomicamente com uma chave idempotente única e persistente.
   Não consome saldo final nem apresenta um cupom antes de confirmar a reserva.
5. Um adaptador Nuvemshop cria o benefício no checkout e persiste o vínculo
   entre resgate, cupom e eventual pedido; falhas exigem compensação da reserva.
6. Consumidor segue ao site para aplicar a recompensa. No primeiro estágio
   será exibido um **cupom individual** e botão “Copiar código” caso não
   exista aplicação automática oficial testada.
7. Um pedido pago confiável com o desconto registrado, tenant, consumidor e
   recompensa corretos gera o consumo definitivo dos pontos **uma vez**.
8. Pedido não pago, expirado, cancelado ou não utilizável exige reconciliação
   e liberação da reserva; reembolso exige ajuste/estorno auditável.

**Nunca** consumir pontos definitivamente ao mero clicar em “Resgatar”,
nem no webhook isolado, nem apenas quando um pedido é criado.

## Primeiro conector de resgate — cupom individual

Usar `POST /coupons`, API oficial Nuvemshop 2025-03, com escopo
`write_coupons` concedido pelo lojista após aprovação e reinstalação.
Revisar na documentação vigente no momento de implementar:
- `type=absolute` para desconto em dinheiro, moeda BRL da loja;
- `code` criptograficamente imprevisível, nunca e-mail/CPF/ID sequencial;
- `max_uses=1`, expiração curta, `min_price` e restrições de acumulação;
- `combines_with_other_discounts=false` como política inicial, sujeita
  a validação de Pix, frete grátis e outras promoções;
- criar o cupom **exatamente uma vez por intenção de resgate**, usar
  estado `provisioning` e reconciliação por código único em caso de timeout;
- não registrar código completo em logs, eventos analíticos ou URL pública.

**Risco obrigatório:** cupom de uso único não autentica quem o utiliza.
Qualquer pessoa que receba o código pode tentar utilizá-lo. O MVP deve
validar identidade/vínculo do comprador na conciliação e a possibilidade
de restrição no checkout antes de disponibilizar uso real; se não houver
barreira adequada, NÃO habilitar emissão a consumidores.

Modelo mínimo proposto:
- `Reward` publicada/versionada; independente de `DiscountRewardDraft`;
- `RedemptionIntent` (tenant, participante, wallet, reward version,
  pontos, validade, idempotency key, status, channel), imutabilidade das
  condições da recompensa na intenção;
- `CouponProvision` (redemption, loja externa, código protegido, cupom ID,
  estado, tentativa, timestamps, expiração);
- `RedemptionOrderMatch` (tenant, canal, order ID oficial, comprovante,
  idempotency key), único por resgate e por pedido;
- eventos de ledger por lote consumindo pontos reservados e transições
  compensatórias. O serviço de pontos já tem `reserve`,
  `cancel_reserve` e `redeem` internos com flag desligada; falta
  política de seleção de lotes, vencimento e integração verificável.

## Automação máxima sem copiar código

A **Discount API** (`read_discounts/write_discounts`) oferece callback
para desconto no carrinho, mas não assumir que identifica um cliente
autenticado: em alguns eventos `customer.id` é nulo. A integração também
precisa respeitar prazo de resposta de callback (800ms informado na doc),
fallback, disponibilidade, proteção de sessão e regras de combinação.

Só migrar do cupom controlado para aplicação silenciosa no carrinho após
comprovar identificador de sessão de resgate confiável, tema/checkout real,
vinculação correta e rollback por expiração. NUNCA instalar script duplicado,
interceptar checkout por DOM não documentado nem editar tema publicado por
essa hipótese.

## Regras transversais

- Conta de outra empresa jamais obtém resgate, cupom ou saldo do tenant.
- Vínculos externos de cliente devem ser comprovados, não apenas nome,
  CPF ou semelhança de e-mail.
- `Order.id` identifica a compra. Pagamento deve ser relido na API
  oficial: status de pedido ≠ pagamento ≠ envio/faturamento.
- Compra anterior à adesão não concede pontos automaticamente.
- Estornos parciais, pedidos reprocessados, corrida entre dois resgates,
  desconto Pix e outras promoções precisam de testes específicos.
- Uma única compra não pode consumir duas recompensas incompatíveis,
  salvo regra publicada que permita tal combinação.
- Limite de custo por lojista e orçamento indisponível devem bloquear
  ou sinalizar inviabilidade antes de ativação; não declarar margem
  positiva apenas porque o desconto nominal é pequeno.
- PII e token OAuth criptografados / minimizados; TTL, retry/backoff,
  idempotência e falhas parciais em todos os pontos de escrita.

## Contrato com os módulos implementados em 13/11

O que existe de fato em `homolog`:
- `ProgramHub.tsx`: editor de `DiscountRewardDraft` **não publicado**;
- `CampaignGuide.tsx`: planejamento de pontos extras **sem disparo**;
- `MemberClub.tsx`: layout de carteira, catálogo, histórico e “Como
  usar no site”; o backend ainda responde saldo `null` e catálogo vazio;
- `PointWallet`, `PointLot`, `PointEvent`, `PointEntry` em modelo
  separado do cashback BRL, sem autorização de escrita em runtime;
- `BenefitCostOverview.tsx`: simulação de custo nominal, não lucro;
- integração Nuvemshop de **leitura** de pedidos/eventos, mas ainda sem
  conexão compra → lote de pontos → resgate.

**Não existe hoje:** publicação de recompensa, cupom Nuvemshop por API,
reserva vinculada a resgate, checkout com desconto aplicado, consumo por
pedido pago, reversão completa ou campanha enviada.

## Aceite para piloto Nuvemshop

- [ ] Duas lojas com integrantes diferentes: isolamento testado.
- [ ] Cliente recebe pontos somente depois de compra paga verificada.
- [ ] Eventos repetidos e reconciliações fora de ordem não duplicam pontos.
- [ ] Saldo disponível, pendente e a vencer têm origem verificável.
- [ ] Uma recompensa publicada aparece no Meu Clube com valor/condições reais.
- [ ] Resgate concorrente não ultrapassa saldo; intenção é idempotente.
- [ ] Cupom criado por única intenção, uso autorizado e desconto presente
      no pedido pago correto (inclusive compras por Pix com promoção vigente).
- [ ] Resgate expirado/abandonado devolve pontos e invalida cupom.
- [ ] Reembolso parcial/total e cancelamento reconciliados.
- [ ] Mobile 320/390/768/1440 e acessibilidade/teclado validados.
- [ ] Backup, migrações, checkout sintético e depois piloto aprovado.
- [ ] **Nenhuma criação real de cupom na Bibelô antes de autorização.**

## Fontes oficiais

- [Nuvemshop API 2025-03: Coupon](https://nuvemshop.dev/en-US/api/resources/2025-03/coupon)
- [Nuvemshop API 2025-03: Discounts](https://nuvemshop.dev/docs-api/resources/2025-03/discounts)
- [Nuvemshop: Authentication & scopes](https://nuvemshop.dev/docs-api/authentication)
- [Nuvemshop API 2025-03: Order](https://nuvemshop.dev/docs-api/resources/2025-03/order)

Plano de negócio e produto:
[Notion — Plano mestre v0.4](https://app.notion.com/p/4178f612deaf8157abc0f5c76ef47b38).
Diário de implementação:
[Notion — Entrega v0.4](https://app.notion.com/p/4178f612deaf8172a34fccd5fc1085be).
