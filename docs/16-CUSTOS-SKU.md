# Registro de custos por SKU — primeira implementação

**Estado:** PR #8, cadastro interno/manual por loja; não importamos preços, custos, estoque ou dados reais da Nuvemshop e do ERP Avanço.

## Objetivo
Resolver a maior limitação das simulações: o custo de mercadoria precisa ter origem e data de conferência para fazer sentido um cashback protegido por margem. A interface permitirá ao lojista cadastrar itens/variantes e consultar quais têm custo desconhecido, custo a conferir e custo pronto para simulação.

## Identificação
- Cada item possui referência interna obrigatória e única na loja, SKU opcional e ID de variante externa opcional.
- SKU não é chave primária universal. O mapeamento real deve usar IDs de produto/variante e SKU/EAN verificados durante a integração.
- ID de variante externa, quando informado, não pode duplicar no mesmo tenant. Nenhuma chamada à Nuvemshop é feita nesta versão.
- Preço de venda salvo é manual e **não comprova preço atual na vitrine**. Os custos não são garantidos pelo ERP Avanço.

## Confiabilidade
- Custo ausente é NULL, não zero.
- Custo positivo declarado manualmente começa com o estado **A conferir**.
- Somente owner/admin pode marcar **Conferido pelo lojista**, com uma descrição de origem de pelo menos oito caracteres. Isso não significa auditoria oficial do ERP.
- Alterar custo, SKU, referência, ID da variante ou nota de origem retira a conferência anterior. Alterar somente preço não revoga a conferência do custo.
- O item fica **Pronto para simular** apenas quando há custo conferido manualmente e preço de venda informado.
- Conferência apenas informa a origem declarada; não dá autorização para campanha, cashback ou desconto.

## API
- GET /api/v1/tenants/{tenant_id}/cost-items/?q=&status=&limit=30&offset=0 lista com resumo por estado, somente membro da loja.
- POST /api/v1/tenants/{tenant_id}/cost-items/ cria item, somente owner/admin; conflitos de referência ou variante retornam HTTP 409.
- GET /api/v1/tenants/{tenant_id}/cost-items/{item_id}/ consulta um item.
- PATCH /api/v1/tenants/{tenant_id}/cost-items/{item_id}/ altera item, owner/admin, exigindo expected_version; conflito de versão retorna 409.
- GET /api/v1/tenants/{tenant_id}/cost-items/{item_id}/history/ consulta 30 entradas recentes do histórico.
- Nenhum DELETE/ações em lote/integração com loja nesta fase.

Todos os valores são inteiros em centavos, nenhum float. Histórico CostAudit é aditivo, com estado anterior e posterior, usuário e data.

## Segurança e QA
- Usuário sem vínculo não vê registros nem consegue editar outra loja, mesmo conhecendo UUID.
- Analyst somente consulta; Owner/Admin cadastram e atualizam.
- Identificadores duplicados não são sobrescritos silenciosamente.
- Campos monetários negativos, nulos indevidos, valores zero e excessivos são rejeitados.
- Paginação e pesquisa limitada para evitar respostas gigantes.
- Django check, makemigrations --check, pytest, Playwright frontend em 390/768/1440, Docker Compose e CI externo têm que passar.

## Integração futura
A [documentação atual de variantes da Nuvemshop](https://tiendanube.github.io/api-documentation/resources/product-variant) confirma campos sku, barcode, price e cost (opcional), mas **cost não pode ser presumido presente**; acesso, versão da API e limites precisam ser verificados quando implementarmos OAuth e catálogo. Não escrever valores na Nuvemshop nesta fase.

## Limites
- Cadastro manual de custos não é inventário, não substitui escrituração nem apuração fiscal.
- Não houve qualquer acesso à Bibelô, Nuvemshop, ERP ou Coolify.
- Não publicar em produção e não executar migrations no banco da homologação sem plano de backup e revisão do PR.
