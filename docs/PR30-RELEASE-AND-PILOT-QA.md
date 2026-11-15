# PR #30 — Encerramento do desenvolvimento e homologação do MVP

## Regra principal

**Terminar o PR #30 não significa habilitar benefício real na Bibelô.**
A próxima etapa é **homologação controlada do fluxo existente**, não um PR #31
com mais recursos. Nenhum script foi instalado, nenhum GET PSP real foi feito
e nenhuma flag de dinheiro foi ligada neste corte.

## O que está pronto no código

1. Pagar.me v5: GET HTTPS de charge e de TODOS os tipos de recebível
   (`payables?charge_id=...`), cursor completo, rejeição de chargeback,
   estorno, splits, recebedor alheio e dados incompletos. Nunca aceitar taxa
   enviada pelo browser/lojista; calcular o líquido somente de recibo PSP.
2. `VerifiedPspFeeReceipt` guarda valores brutos, taxa, valor líquido e hash
   do snapshot, ligado ao `VerifiedPaymentProof` e tenant. Trigger PG
   impede UPDATE/DELETE. Caso de espera de liquidação: manter NO-GO.
3. A conciliação de SKU do PR #29 utiliza tarifa proveniente do recibo PSP
   antes do cálculo de pontos/cashback, sem aceitar override manual.
4. NubeSDK worker de QA: `has_cart_validation`, `cart:validate`,
   `coupon:remove` e falha fechada em rede. Sem DOM nem CSS injetado.
5. Endpoint de eligibility devolve **somente** `{"eligible": boolean}`;
   aceita código + e-mail do checkout SOMENTE junto com token de curta duração,
   emitido após sessão comprovada no portal de cliente; cache com rate-limit
   e CORS por origem HTTPS autorizada. A comparação não revela dados do titular.
6. Comando `set_loyalty_release --mode commercial ... --dry-run` emite
   `READY_FOR_HOMOLOG_ACTIVATION` quando há base de loja/programa/OAuth
   cadastrada. Não altera o tenant nem faz requisições externas. A mensagem
   `NO_GO_COMMERCIAL` permanece até as homologações reais.

## Limitações importantes

- **O email no checkout pode ser digitado por qualquer pessoa.** A posse de
  um token de sessão verificada do clube também pode ser compartilhada. A
  checagem client-side **não é prova de titularidade que possa autorizar
  descontos monetários em caráter comercial**.
- O token emitido no portal do clube **não é automaticamente transferido**
  ao sessionStorage do worker NubeSDK; integração autorizada entre os dois
  domínios e prova de não-bypass permanecem para QA. Não copiar bearer em
  query strings, logs ou analytics.
- O arquivo `integrations/nuvemshop/checkout-eligibility.nube.ts` é fonte
  para um projeto NubeSDK dedicado, não bundle de produção. A URL placeholder
  deve ser configurada na build e CORS liberado somente para o host da loja QA.
- A criação/associação do script depende do Partner Portal: habilitar
  permissão Scripts, criar script com **Uses Nube SDK**, publicar bundle
  em loja demo e verificar SDK ativo; somente depois considerar API /scripts
  conforme contrato oficial e OAuth da instalação. Nunca instalar na Bibelô
  sem autorização específica.
- Em payables `waiting_funds`, refunds, chargebacks, ausência de taxa ou
  tarifa variável: bloquear o crédito; liquidado é um estado distinto de
  captura. Teste sintético pode demonstrar cálculo, mas não autentica
  taxa do mundo real.
- `FIDELIZA_CHECKOUT_OWNER_ENFORCEMENT_VERIFIED=False` e
  `FIDELIZA_PSP_FEE_RECONCILIATION_VERIFIED=False` permanecem hardcoded
  OFF. Não usar `override_settings` em produção.
- O gate de SKU já verifica 100% das variantes e os itens vendidos;
  **nenhuma** escrita financeira pode ignorá-lo.

## O que fazer AGORA, sem adicionar funcionalidades

1. Integrar PRs #25 → #28 → #29 → #30 em uma branch exclusiva
   de homologação, resolver migrações e executar backup no ambiente QA.
2. Rodar migration/checks e testes smoke em PostgreSQL descartável;
   publicar preview no Coolify, nunca diretamente no ambiente comercial.
3. Cadastrar **um** participante teste no portal, validar e-mail e registrar
   o vínculo com a loja; conferir sua área pública de saldo/recompensas.
4. Comprar com uma conta de teste e PSP sandbox; comprovar: order ID interno
   versus número legível, captura, taxa, custo SKU, desconto, frete e crédito
   provisório. NÃO executar compra real não autorizada.
5. Simular desconto de R$ 5 com cupom único, testar uso pelo titular,
   tentativa de terceiro, cancelamento, revogação e retorno idempotente
   quando comprovadamente não utilizado.
6. Navegar no checkout QA com NubeSDK DevTools: confirmar que
   `cart:validate` interrompe passagem ao pagamento quando falha;
   tentar navegador privado, JavaScript desligado, outro navegador,
   sessão vencida e chamada direta ao checkout. Se houver bypass,
   manter NO-GO comercial.
7. Verificar fluxo de loja física/WhatsApp depois do piloto virtual
   básico. Ajustar telas Visão Geral, Programa, Cliente e Recompensas
   com base em observação de usuários, não por preferência de dev.

## Critério de aprovação

**Homologação funcional:** cadastro → compra → prova de pagamento →
pontos provisórios → consulta do cliente → recompensa → resgate em QA.

**Go-Live comercial:** exige enforcement de titularidade no desconto
comprovadamente não contornável no checkout, taxa PSP real auditável,
fiscal/estornos reconciliados, flags explicitamente habilitadas, e aprovação
humana do ticket + SHA. Sem qualquer um deles: **NO-GO**.

Fontes:
- https://nuvemshop.dev/apps/nube-sdk/getting-started
- https://nuvemshop.dev/apps/nube-sdk/events/coupon
- https://nuvemshop.dev/apps/nube-sdk/events/cart
- https://docs.pagar.me/reference/retornando-receb%C3%ADveis
