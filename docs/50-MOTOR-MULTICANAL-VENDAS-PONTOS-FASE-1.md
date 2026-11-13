# 50 — Motor multicanal de vendas e pontos · Fase 1

**Projeto:** Vidalys Fideliza. **Data:** 13/11/2026.
**Branch:** `homolog`. **Regra inegociável:** Nuvemshop é somente um canal de vendas,
não o cadastro mestre do programa; a carteira pertence ao participante por tenant.

## Contrato de negócio validado

- Participante com adesão e identidade verificadas compra num canal
  (Nuvemshop, balcão ou futuramente Vidalys Flow/WhatsApp).
- A origem identifica a compra; pagar não implica pontuar sem verificar status
  financeiro, valor elegível, regra vigente, cliente e duplicidade.
- Uma compra **posterior à adesão** pode gerar pontos `pending` após
  verificação. Liberar como `available` só após carência, conforme regulamento.
- Comprador que não aderiu **não recebe pontos**. Pode ser alvo de convite
  autorizado (não registrar publicidade ou PII sem fundamento).
- Venda anulada, devolvida ou parcialmente reembolsada requer ajuste/estorno.
- A mesma venda no mesmo canal/loja não pode pontuar duas vezes. É permitido
  manter registro de venda não participante **sem nome/CPF/telefone** para
  avaliar oportunidades agregadas, sem crédito retroativo implícito.
- Pontos e cashback são unidades distintas e exigem carteiras distintas.

## Implementação da Fase 1

Novo app `apps.sales`, sem endpoints que escrevam em `CashbackWallet`
nem que habilitem `FIDELIZA_LEDGER_WRITES_ENABLED`:

- `SaleRecord`: `tenant`, `channel`, referência documental, participante
  opcional, valor elegível em **centavos BRL**, timestamp informado, evidência
  de cupom/recibo sem conteúdo sensível, usuário que registrou, conferência
  e estado. `UNIQUE(tenant,channel,external_reference)`.
- `PointRuleDraft`: um rascunho versionado por tenant, fator de conversão
  em inteiros, carência e validade. Não permite ativação.
- `GET/POST /api/v1/tenants/{tenant_id}/sales/manual/`:
  listar 30 registros ou registrar venda **somente do canal balcão**;
  data em ISO8601 com timezone e referência única. A lista tem proteção
  de sessão e `Cache-Control: no-store`.
- `POST /api/v1/tenants/{tenant_id}/sales/manual/{sale_id}/review/`:
  revisão por owner/admin **diferente do operador que cadastrou**.
  Uma segunda pessoa precisa conferir evidência e justificativa;
  a conferência administrativa **não é comprovação independente PSP**.
- `GET/POST /api/v1/tenants/{tenant_id}/loyalty/point-rule-draft/`:
  ver e salvar a simulação da regra; retorna `activation_available=false`.
- Frontend: menu **Vendas** mostra entradas de balcão e conferência; menu
  **Programa** guarda o rascunho de pontuação. Nada de duplicar regras
  em Configurações ou Clientes.
- Para pessoas fora do clube, `participant_id=null` resulta em
  `awaiting_member`, sem gerar pontos.
- Se a venda ocorrer antes de `max(consent_at,joined_at)`, nenhuma venda
  participante é registrada como elegível; conversão retroativa exigirá
  campanha explícita e será tratada separadamente.
- Senhas, CPF, dados de cartão e dados pessoais em comprovantes **não são
  armazenados**. O campo é apenas uma referência operacional.

### API de registro de balcão (exemplo sintético)

```json
{
  "reference": "VENDA-00042",
  "eligible_amount_cents": 10000,
  "participant_id": null,
  "reported_paid_at": "2026-11-13T15:00:00-03:00",
  "evidence_reference": "CUPOM-00042"
}
```

Um POST repetido com corpo idêntico retorna `already_recorded=true`;
um POST com a mesma referência e informações diferentes retorna HTTP 409.
A operação nunca é idempotente por simples proximidade de tempo; usa a
identidade da venda.

### Regra de pontos em rascunho (exemplo, não ativo)

```json
{
  "points": 1,
  "per_cents": 100,
  "hold_days": 7,
  "validity_days": 180
}
```

Isso significa **1 ponto a cada R$1,00 elegível** com arredondamento para
baixo, sete dias de carência e validade de 180 dias **após liberação**,
se vier a ser publicado. Sem regra publicada, nenhum crédito é gerado.
A base elegível real ainda precisa definir produto, frete, descontos,
tributos, gift card e devoluções no contrato v1 antes de ativação.

## Como conectar a Nuvemshop sem duplicar serviços

O projeto já dispõe de `order/paid` e `order/updated` autenticados e
idempotentes, além de leitura oficial da Order via GET sob `read_orders`.
**Não recriar OAuth, webhook nem carteira financeira.**

Documentação oficial da API Nuvemshop 2025-03:
https://nuvemshop.dev/docs-api/resources/2025-03/order

- Webhook é sinal de reconciliação, não prova financeira isolada.
- `payment_status=paid` e `paid_at` representam pagamento no pedido;
  verificar gateway, `total_paid_by_customer`, cancelamentos e eventos
  adicionais. Gateway `internal` sinaliza pagamento marcado manualmente,
  não deve ser tratado como confirmação independente.
- O ID da compra é `Order.id`, não o número exibido (`number`).
- `Order.customer` pode exigir `read_customers`, e o vínculo com
  `ProgramParticipant` deve ser por identidade comprovada daquela loja.
- Próxima integração usa o serviço normalizado de `SaleRecord` somente
  depois de revalidar loja, token, cliente, status e valor, sob chave
  `tenant:nuvemshop:order_id`, sem crédito ou importação implícitos.

## Gate e pendências explícitas

1. **Primeiro:** CI verde, migrations check, backup e deploy do SHA em
   homologação, aplicando `sales.0001_initial` (não em produção).
2. Testar dois administradores, uma venda participante e uma não participante,
   replay da referência e prova de nenhum saldo alterado.
3. Produto mínimo para operação de uma pessoa: desenhar autoatestado do owner
   com limites/2FA ou revisão de comprovante independente; **não contornar
   silenciosamente a dupla conferência**. Enquanto isso, o único dono
   consegue registrar a venda, mas não concluir sua revisão sozinho.
4. Integrar pedido Nuvemshop de loja piloto, `read_orders` e identidade
   segura, com estado de pagamento verificado; apenas consulta inicialmente.
5. Construir **PointWallet/PointLedger** independente da carteira BRL:
   entrada pendente, liberação, vencimento, estorno e reserva, provas por
   compra, chave de idempotência, testes de concorrência e orçamento.
6. Construir recompensa real aplicada ao checkout/PDV/Flow antes de
   disponibilizar botão de resgate no Meu Clube.

**Proibido nesta fase:** cashback automático, pontos ativos, indicação
paga, importação de pedidos antigos para crédito, exceção silenciosa
na conciliação ou publicação da configuração como benefício real.
