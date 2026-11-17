# 52 — Nuvemshop: ciclo de vida da instalação e diagnóstico

**Data:** 17/11/2026. **Estado:** implementado na branch `feature/diferenciais-clube`.
**Efeito financeiro:** nenhum. Nenhuma flag `POINTS/LEDGER/PSP/CHECKOUT` foi ligada.

## O que mudou

1. **`app/uninstalled`** — `POST /api/v1/webhooks/app/uninstalled/`, HMAC
   `x-linkedstore-hmac-sha256` com o client secret. Marca
   `NuvemshopInstallation.uninstalled_at` (idempotente; mantém a primeira data).
   Não apaga nada: a limpeza continua sendo do `store/redact`.
   Depois disso a instalação não conta como conectada, não recebe avisos de
   pedido e não dispara releitura. Reinstalar pelo OAuth zera o campo.
2. **Pedidos cancelados/anulados** — `POST /api/v1/webhooks/orders/cancelled/` e
   `/orders/voided/` entram na mesma caixa de eventos, só como gatilho de
   releitura. A releitura continua tratando apenas `order/paid` como pagamento.
3. **Status da conexão** — `GET .../nuvemshop/status/` passa a devolver
   `uninstalled_at`, `last_order_event_at` e `next_step="reinstall_app"`.
4. **Configurações** — diagnóstico em linguagem simples (app preparado, loja
   autorizada, leitura de produtos/pedidos/clientes, avisos chegando, acesso
   confirmado agora). Linha sem resposta aparece como "não verificado", nunca "ok".

## Para ativar na loja de teste (não na Bibelô real)

1. Migração: `python manage.py migrate nuvemshop` (0012, só adiciona coluna e choices).
2. No Portal de Parceiros, cadastrar os webhooks do app:
   - `app/uninstalled` → `https://<api>/api/v1/webhooks/app/uninstalled/`
   - `order/cancelled` → `https://<api>/api/v1/webhooks/orders/cancelled/`
   - `order/voided` → `https://<api>/api/v1/webhooks/orders/voided/`
3. Desinstalar e reinstalar o app na loja de teste e conferir o diagnóstico.

## Testes

`backend/apps/nuvemshop/test_app_lifecycle.py`: assinatura obrigatória, tipo
desconhecido, idempotência, isolamento entre lojas, bloqueio de eventos após
desinstalação, cancelado/anulado sem efeito financeiro, tópico divergente da
rota e status com `reinstall_app`.
