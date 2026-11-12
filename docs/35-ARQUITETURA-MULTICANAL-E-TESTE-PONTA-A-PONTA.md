# Vidalys Fideliza — arquitetura multicanal e jornada de homologação

Data da decisão: 11/11/2026 (America/Sao_Paulo).
Status: **proposta arquitetural documentada; não é integração ativa**.
Referência de código: branch `homolog`.

## Decisão de produto

O Fideliza será **independente do canal de venda**. Nuvemshop será a
primeira integração, mas o produto deverá admitir:
- outras plataformas de e-commerce com autenticação e eventos próprios;
- loja física, com ERP/PDV ou cadastro de venda comprovada;
- WhatsApp, com pedidos confirmados por integração autorizada;
- operação híbrida da **mesma loja**, sem dobrar benefícios do mesmo pedido.

Não apresentar suporte a esses canais na interface como se já
estivesse ativo. A jornada existente permanece orientada à Nuvemshop
até a implementação e homologação de adaptadores separados.

## O que o código atual já favorece

- `Tenant.id` é UUID interno, único por loja.
- `ProgramParticipant.id` é UUID interno, vinculado ao tenant.
- `CashbackWallet` pertence a um participante do tenant;
  `CashbackEvent` tem chave de idempotência e ledger imutável.
- A análise de rentabilidade não escreve na plataforma externa.
- OAuth e importação específica Nuvemshop estão num app separado.

## O que ainda acopla o sistema à Nuvemshop

- `Tenant.platform` e `Tenant.external_store_id` pressupõem uma
  plataforma principal para cada loja.
- `ProgramParticipant.external_customer_id` usa uma referência
  externa única por tenant. Não basta para identificar um comprador
  que aparece no PDV, WhatsApp e Nuvemshop com IDs diferentes.
- `EnrollmentCustomerLink.external_customer_id` é da Nuvemshop.
- A comprovação de pagamento do pedido ainda não está implementada
  como evento de origem independente da plataforma.
- O motor de concessão do cashback **não está ativado** e não deve
  ser simulado como receita real.

## Contrato proposto, não aplicado nesta entrega

### 1. SalesChannel (novo modelo, migração futura)

`tenant_id`, `kind` (`nuvemshop`, `shopify`, `woocommerce`,
`pos`, `whatsapp`...), `external_account_id`, status,
referência à credencial cifrada, permissões, data de vínculo.

Um tenant poderá ter vários canais; cada conta externa
pertencerá a um único tenant. Migrar o vínculo Nuvemshop existente
**sem recriar ou reatribuir lojas**. Nunca promover para produção
sem amostra representativa e teste de rollback.

### 2. CustomerIdentity (novo modelo, migração futura)

`participant_id` interno + `channel_id` + `external_customer_id`
+ prova de identidade e data da validação. Identificar por canal
não é prova de que duas contas pertencem à mesma pessoa.
Vínculo híbrido exige login/OTP/consentimento verificável e
resolução de duplicidade administrada. Não unir clientes por
nome, telefone ou e-mail semelhante.

### 3. VerifiedOrder (fatos de compra normalizados)

`tenant`, `channel`, `external_order_id`, `participant`,
`paid_amount_cents`, moeda, `payment_status`, `paid_at`,
`refund_status`, origem e evidência verificável.

- Nuvemshop: somente após validação oficial do estado do pedido
  e das notificações de pagamento.
- PDV/ERP: somente após confirmação do caixa/ERP autenticado,
  inclusive possíveis cancelamentos.
- WhatsApp: mensagem não comprova compra. Exigir confirmação de
  pagamento do PSP/ERP ou conciliação comprovada.
- Uma mesma compra recebida por duas integrações não pode gerar
  duas concessões; chaves e referências precisam deduplicar.

### 4. BenefitRule, Wallet e ledger

Uma regra pode valer para um ou mais canais, com margem, teto,
prazo, elegibilidade, estorno e reserva. A carteira continua
**uma por participante**, com movimentações por canal e origem,
mantendo o ledger e a auditoria centralizados.

### 5. Segurança e privacidade

Cada canal deve validar assinatura/credencial, idempotência,
retry/backoff, eventos fora de ordem e isolamento multi-tenant.
Solicitação LGPD precisa mapear todas as identidades relacionadas
ao mesmo participante e afetar somente os dados controlados
pela Vidalys, respeitando retenção e prova. Tokens e payloads
de pagamento nunca devem aparecer ao lojista.

## Sequência para o teste do fluxo ainda hoje

| Etapa | Situação na homolog (código) | Como testar sem risco |
|---|---|---|
| Login e escolha de loja | implementado | login de lojista de teste |
| Nome e cores do clube | implementado | alterar, salvar, recarregar |
| Conexão Nuvemshop | OAuth implementado, depende de env/instalação | loja e credenciais de teste |
| Regulamento e convite | implementado, flags inicialmente OFF | aceite com dados sintéticos |
| Confirmação de e-mail | implementada, flag e SMTP inicialmente OFF | caixa controlada de teste |
| Prévia do vínculo de cliente | implementada, flag OFF | cliente sintético da loja |
| Aprovação da participação | implementada, flag OFF | aprovar participante verificado |
| Consulta da carteira interna | implementada, somente leitura | ledger sintético, sem resgate |
| Simulação da rentabilidade | implementada | dados fictícios e orçamento |
| Rascunho de campanha | implementado, **não publica** | salvar, reabrir, revisar |
| Pedido real pago -> concessão | **pendente** | não afirmar conclusão |
| Liberação/uso real de cashback | **pendente** | não alterar saldo real |
| Cancelamento/estorno real | **pendente** | apenas testes unitários do ledger |
| Integração loja física/WhatsApp | **futura** | sem ativação |

**O fluxo real de cashback ponta a ponta não estará pronto apenas
pelo fato de o painel ficar visualmente aprovado.** Primeiro é
necessário implementar proveniência de pedido pago, elegibilidade,
idempotência entre fontes, estorno e prova de uso.

## Checklist de apresentação e interface

Cobrir 320, 360, 390, 430, 768, 1024, 1440px; conferir:
- sem rolagem horizontal ou botões escondidos;
- menu móvel com foco/teclado, `Escape`, foco restaurado e
  controles fora da tela inacessíveis;
- formulários sem zoom automático no Safari iOS;
- contraste legível mesmo quando o lojista escolhe cores claras;
- mensagem clara sobre recurso real, prévia ou indisponível;
- identidade visual jade/navy/mint/dourado consistente;
- confirmação e erros de operação acessíveis e sem segredos.

Registrar evidências em Playwright e CI do SHA exato. O site público
`/demo` é **ilustrativo**; gráficos ou valores exibidos na demo
não comprovam vendas ou cashback real.

## Escopo desta revisão

Sem migração de canais, sem atualização de `main`, sem deploy Coolify,
sem alteração na loja Bibelô e sem habilitar recursos financeiros.
Primeiro estabilizar a UX e validar os fluxos da homologação.

## Pré-voo read-only disponível na homologação

Após implantar o commit aprovado em um ambiente de teste, executar
dentro do container de API:

```sh
python scripts/inspect_loyalty_journey.py --slug loja-piloto
```

Substituir `loja-piloto` pelo **slug da loja de homologação** que já
existe no sistema. O comando não cria dados, não chama APIs externas,
não ativa recursos e não revela nome/e-mail de participantes,
segredos, saldos, pedidos ou tokens. Ele lista somente estados
verificáveis e contagens internas daquele tenant.

Atenção: `email_delivery_flag_enabled=true` não comprova recebimento
no SMTP2GO; o envio deve ser testado com caixa de e-mail controlada.
`paid_order_verification_available=false`,
`live_cashback_granting_available=false` e
`live_redemption_available=false` permanecerão falsos nesta etapa.

O script não deve ser usado como substituto para o teste humano e
integração ponta a ponta na Nuvemshop.
