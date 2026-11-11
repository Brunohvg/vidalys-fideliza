# Rascunhos de campanhas: salvar e retomar planejamento

Data: 11/11/2026. Branch: `feat/campaign-drafts-guided-v1`, baseada no
visual aprovado `design/loyalty-experience-v2`.

## Por que essa etapa existe
A pessoa lojista pode escolher um objetivo, informar orçamento e percentual,
guardar a configuração e voltar mais tarde sem reiniciar. A UI principal
continua simples: Objetivo → Benefício → Prévia. Rentabilidade é opcional.

## Contratos
- `GET /api/v1/tenants/{tenant_id}/campaign-drafts/`: até 30 rascunhos da
  própria loja, com prévia calculada no servidor.
- `POST /api/v1/tenants/{tenant_id}/campaign-drafts/`: cria rascunho;
  somente proprietário ou administrador, sessão + CSRF.
- `GET /api/v1/tenants/{tenant_id}/campaign-drafts/{draft_id}/`: detalha.
- `PATCH /api/v1/tenants/{tenant_id}/campaign-drafts/{draft_id}/`: atualiza
  com `expected_version` para evitar sobrescrever outra sessão.
- `DELETE` não está disponível nesta fase; retenção/exclusão ainda exige contrato.

Campos: `title`, `goal` (segunda compra, reativação, recorrência),
`cashback_rate_bps` (1 a 1000), `ticket_cents`, `projected_paid_orders`
(1 a 50.000) e `budget_cents`. Campos de implantação ou aprovação são
rejeitados. Os números são **hipóteses do lojista**, não dados Nuvemshop.

O cálculo de prévia do servidor usa HALF_UP em centavos para crédito por pedido,
estimativa de exposição máxima e comparação de orçamento. Não verifica margem
real, taxa de pagamento, frete, imposto nem estoque.

## Garantias
- Todo acesso requer membership no tenant; acessos cruzados recebem 404.
- Analista pode consultar, mas não salvar ou alterar.
- Cache privado `no-store`, limite de 30 rascunhos por loja,
  controle de versão e transação na atualização.
- Um rascunho **nunca é uma campanha ativa** e não cria cupom, benefício,
  desconto, cliente, evento financeiro ou comunicação.
- O frontend não salva em `localStorage`; utiliza a API autenticada.
- Nenhum script é instalado na vitrine, nem alterações na Bibelô.

## QA
Testes Django: isolamento, permissões, campos rejeitados, valores inválidos,
persistência, prévia, conflito de versão e limite.
Playwright: salvar e retomar em 390, 768 e 1440 px, sem botão de publicar
e sem rolagem horizontal. Validar CI e capturas antes de homologação.

## Próximo incremento
Importar indicadores agregados e clientes somente após autorizações oficiais
da Nuvemshop e fluxo de consentimento. Manter separados compradores,
participantes verificados e pessoas convidadas.
