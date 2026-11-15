# PR #28 — Consolidação, segurança e migrações sem colisão

**Base única:** PR #25 (SHA 98dd934080a419162afbc39f67591eb10c969171).
**Código consolidado:** estrutura PSP, cupom e 10 triggers do PR #27 + CPF/HMAC do PR #26; sem realizar merge dos dois históricos divergentes.
**Estado:** draft, CI obrigatório, nenhum deploy, migração ou operação em loja real.

## Mapa das migrações (por app, sem renumerar apps diferentes)
- customers: `0001` → `0002` → `0003_verified_cpf_kind` (trazido do PR #26).
- loyalty: `0001` → `0002` → `0003` → `0004_financial_proofs` → `0005_immutable_payment_proofs` (mantidos do PR #27).
- nuvemshop: `0001` ... `0007` → `0008_coupon_revocation_proof` → `0009_immutable_revocation_audit` → `0010_verified_unused_before_revocation`.
- tenants: `0001` → `0002` → `0003` → `0004_loyalty_live_optin`.
- A migração alternativa `loyalty/0004_immutable_payment_proof` e `nuvemshop/0008_coupon_revocations` do PR #26 NÃO foram copiadas; migrar uma única linhagem, nunca aplicar os dois conjuntos.
- Mantidas 10 triggers: 6 ledgers legados, 3 provas financeiras e 1 auditoria de revogação.

## Cupom expirado inválido, mas não utilizado
- `valid=False, used=0, deleted_at=None` **não é exclusão**: solicitar DELETE mesmo quando cupom já expirou; depois exigir GET 404 ou `deleted_at`, com código e uso conciliados.
- Persistir `verified_unused_at` após GET externo mostrar `used=0`, antes do DELETE. Um GET 404 prévio sem prova de unused não devolve saldo.
- Expiração exige 30 minutos de carência, ausência de vínculo de pedido e compensação do MESMO lote; repetir é idempotente.
- Pedido cancelado/estornado não gera retorno automático com base apenas na inexistência de prova PSP local: cupom pode ser revogado, mas a reserva permanece para conciliação de não captura.
- Estados incertos conservam a reserva; jamais marcar `valid=False` como confirmação de revogação.

## Cobertura de 100% dos custos de variantes compráveis
- Consultar o catálogo da instalação OAuth autorizada integralmente, todas as páginas até lote final; falha/limite = **NO-GO**.
- Conferir cada variante de `visible` e `unlisted` (comprável por link), excluindo `hidden`.
- Cada variante precisa de `id`, SKU não vazio, associação exata `external_variant_id` + SKU com `CostItem`, custo e preço positivos, `verified_at` e `verified_by`. Variações sem SKU e IDs alterados falham.
- Apenas catálogo local ou um SKU conferido não prova 100%. Exigir `read_products` além de `read_orders` e `write_coupons`.
- Fazer GET remoto antes da transação de ativação para não prender o lock durante HTTP; revalidar tenant e regras ao persistir.
- Mudanças futuras no catálogo continuam bloqueadas pelo motor de custos de cada venda, mas exigem rotina de verificação periódica antes da operação comercial real.

## Titularidade
- Consultar CPF apenas se prova `provider_confirmed` já existir e armazenar exclusivamente HMAC com escopo tenant; nenhum CPF de checkout vira prova por si só.
- `order_recheck_service` exige correspondência de CPF, e-mail e telefone apresentados, para o mesmo perfil antes de aceitar o match do cupom.
- `FIDELIZA_PREISSUE_OWNERSHIP_CHECK_ENABLED`: ao ativar em teste, exige perfil/contato verificado do participante antes de emitir o cupom.
- `FIDELIZA_CHECKOUT_OWNER_ENFORCEMENT_VERIFIED` segue hardcoded False. A checagem antes da emissão NÃO restringe quem pode digitar o código na Nuvemshop. Só aprovar comercial após enforcement comprovado antes de aplicar desconto. A API de descontos com callback é candidata para homologação, não uma capacidade presumida.

## Testes
- Revogação sintética de cupom inválido sem uso; 404 sem prova; timeout; idempotência; tentativas de uso/cancelamento; trigger PG.
- Comando comercial com catálogo parcialmente conferido (recusa) e 100% conferido (aprova SOMENTE no teste com gates simulados); `unlisted` conta e `hidden` não conta.
- CPF HMAC, preflight de emissão, recusa de contato divergente.
- Backend `pytest`, PostgreSQL descartável com `manage.py test`, `makemigrations --check --dry-run`, frontend e 139 Playwright via CI.

## GO / NO-GO
- GO somente para revisão técnica quando CI do SHA final estiver 6/6 e migrações verificadas.
- **NO-GO comercial:** não há restrição preventiva efetiva de uso do cupom no checkout, nem E2E com Pagar.me e loja QA reais.
- Flags de dinheiro, prova PSP e ativação comercial permanecem OFF em runtime. Não executar na loja Bibelô sem autorização específica.
