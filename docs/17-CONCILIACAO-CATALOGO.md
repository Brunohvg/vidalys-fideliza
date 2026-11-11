# Conciliação de catálogo Nuvemshop — prévia segura P0

Estado: PR #9 em desenvolvimento. Não é integração OAuth ativa. Nenhum token conectado, consulta ao vivo, escrita de catálogo ou cashback.

## Objetivo

A Nuvemshop pode recriar IDs de variantes ao alterar atributos. Unir automaticamente registros só pelo SKU pode associar custo errado. Este módulo apresenta divergências antes de qualquer importação.

## Amostra

A interface aceita arquivo JSON local ou conteúdo colado. O botão de exemplo usa produtos totalmente fictícios.

Limites: 15 produtos, 50 variantes, 150 KB. É possível enviar o array da resposta GET /products ou um objeto de nível superior com chave products. Campos:
- Produto: id, name (texto ou tradução pt/es/en), variants.
- Variante: id, product_id, sku, barcode, price, promotional_price, cost.
- SKU e barcode/EAN sempre texto (não converter em número; preservar zeros iniciais).
- Valores monetários em decimal de texto e centavos exatos; cost e price podem ser desconhecidos.
- Entrada inválida e chaves extras no topo geram erro; não inserir credenciais ou dados de clientes.

O frontend transmite somente os campos descritos, não descrições HTML, imagens ou dados adicionais.

## Decisão por variante

1. matched — ID de variante coincide com cadastro local e não há divergências conhecidas.
2. review_required — SKU ambíguo ou repetido, ID recriado, custo/preço divergente, mapeamento por SKU ainda não confirmado ou custo local não conferido.
3. unmapped — não há vínculo local.

Código de barras/EAN é apenas dado de apoio; não serve para vínculo automático. SKU candidato nunca remapeia sem revisão. Ausência de custo remoto não vira zero e custo local conferido não é sobrescrito.

Resultados são somente comparativos. As flags writes_performed=0, automatically_approved=false, will_modify_cost=false e will_modify_product=false documentam a ausência de mutações.

## API interna

POST /api/v1/tenants/{uuid}/catalog/reconcile-preview/

Requer login Django com CSRF e associação ao tenant. Analistas podem usar a prévia, mas não alterar custo. POST serve para transportar JSON; o endpoint só realiza SELECT do banco local, sem INSERT, UPDATE ou DELETE.

## Cliente HTTP de leitura (ainda não ligado)

backend/apps/catalog/client.py: GET fixo na API Nuvemshop 2025-03, máximo 15 produtos por página, timeout, 2 MB por resposta, até três tentativas em 429 ou erros 502/503/504, sem redirecionamentos com Bearer. Não há endpoint para informar token nem conexão OAuth instalada.

Antes do uso em loja real: OAuth authorization_code, state validado, store_id confiável, escopo mínimo read_products, credenciais cifradas no backend, controle global de taxa por app/loja e telemetria sanitizada. Toda importação futura precisa ser explícita, com amostra validada, idempotência, trilha de alterações, tratamento de falhas parciais e rollback.

## Referências oficiais (consultadas em 11/11/2026)

- https://tiendanube.github.io/api-documentation/resources/product
- https://tiendanube.github.io/api-documentation/resources/product-variant
- https://tiendanube.github.io/api-documentation/authentication
- https://tiendanube.github.io/api-documentation/intro

## Critérios de aceite

Backend: status de conciliação, variantes recriadas, SKU duplicado, EAN com zeros, custo desconhecido, permissões, limites e nenhuma gravação.
HTTP: URL fixa, GET exclusivo, erros sanitizados e retry.
Interface: file upload local, exemplo fictício, leitura de alertas, filtros, responsividade 390/768/1440 px, sem overflow.
CI: Django, TypeScript, Docker, PostgreSQL externo e Playwright verdes.

PR #9 é empilhado sobre PR #8. Não alterar main, Coolify, Bibelô, Avanço ou Nuvemshop durante esta fase.
