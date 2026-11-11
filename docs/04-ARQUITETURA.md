# Arquitetura do Vidalys Fideliza — v0.1

## Tech stack proposta
Django + Django REST Framework, PostgreSQL, Celery + Redis, TypeScript, Nexo/Nimbus (admin embutido) e Nube SDK (vitrine/checkout), Coolify; CI com pytest e lint. O aplicativo funciona mesmo sem Vidalys Flow. n8n apenas para notificações secundárias, nunca como ledger transacional.

## Componentes de domínio
`tenants`, `integrations`, `customers`, `order_projections`, `campaigns`, `rule_versions`, `wallets`, `ledger_entries`, `reservations`, `redemptions`, `webhook_inbox`, `outbox_events`, `audit_logs`, `subscriptions`.

## Fluxo confiável
OAuth→ loja/tenant; pagou→ webhook validado e deduplicado→ conferir pedido→ crédito pendente; liberação conforme regra→ disponível; autenticação do cliente→ saldo→ reserva transacional→ Discount API→ desconto real; novo pedido pago→ consumo definitivo; falhou/abandonou→ cancelamento/expiração de reserva; devolveu→ contralançamento.

## Integração Nuvemshop
Inspecionar documentação atual da Admin API (OAuth, permissões e versão), webhooks, Discount API (promotions/callbacks), Nube SDK e regras de composabilidade do desconto. Criar POC usando loja autorizada antes de prometer resgate de saldo parcial. Não colocar tokens em browser/Notion/Git. Não editar o tema Ipanema nem duplicar o checkout.

## Segurança
Row-level tenancy por `store_id`, RBAC, testes de acesso cruzado, criptografia de credenciais, webhooks conforme autenticação oficial atual, idempotência, retries e DLQ, auditoria e reconciliação, backup/restauração, logs sanitizados. API de desconto precisa de resposta rápida; objetivo interno p95<400ms a validar com timeout oficial.

## Deploy
Ambientes staging e produção separados; web/worker/scheduler/Postgres/Redis com secrets por ENV, health checks e CI; migrações controladas e rollback. Publicação só após POC documentada.

## Fontes oficiais
https://nuvemshop.dev/apps/getting-started
https://nuvemshop.dev/api/getting-started
https://nuvemshop.dev/docs-api/resources/2025-03/discounts
https://dev.nuvemshop.com.br/en/docs/applications/nube-sdk/state
