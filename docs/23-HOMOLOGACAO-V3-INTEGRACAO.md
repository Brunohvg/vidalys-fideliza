# Homologação v3 — integração dos incrementos aprovados em CI

**Branch:** `integrate/fideliza-homologacao-v3`  
**Base:** `feat/campaign-drafts-guided-v1` (CI individual aprovado).  
**Fontes:** PR #13 (menu), PR #14 (ledger interno), PR #16 (rascunhos).

## Visão de produto
Manter a experiência visual da `design/loyalty-experience-v2`, já
visualizada pelo usuário, e avançar em funcionalidades concretas sem ativar
cashback real. A ordem do produto continua: Visão geral → Clientes →
Campanhas → Resultados. Rentabilidade e SKU permanecem ferramentas avançadas.

## Alterações reunidas
- Menu lateral mais compacto e com barra discreta, respeitando navegação
  por toque e teclado.
- Cliente participante com extrato de ledger **apenas quando existe carteira
  com lançamentos internos**; sem saldo inventado. Sem resgate.
- Backend de carteira em BRL, com eventos idempotentes e gravações bloqueadas
  por padrão (`FIDELIZA_LEDGER_WRITES_ENABLED = False`).
- Salvar, listar, retomar e atualizar rascunhos de campanhas com controle
  de versão; nunca publica, cria cashback ou contata compradores.
- Migrações novas `campaigns/0001` e `wallets/0001`.
- QA Django, TypeScript, Playwright e smoke com banco externo obrigatórios.

## Antes de publicar na homologação
1. Exigir CI **desta branch integrada** verde; CI dos PRs individuais não
   prova ausência de conflito de integração.
2. Inspecionar screenshots em 390/768/1440, interface em desktop e celular.
3. Preservar banco PostgreSQL existente e **executar migrações controladas**.
   Backup/restauração validados antes do deploy; sem recriar banco nem volumes.
4. Atualizar SOMENTE ambiente de homologação autorizado, mantendo variáveis
   de autenticação, CSRF e DB, sem expor segredos.
5. Validar login, isolamento de lojas, lista de participantes, rascunhos e
   regras desativadas usando dados sintéticos ou de teste autorizados.
6. Separar revisão visual e funcional da publicação da Nuvemshop/Bibelô.

## Bloqueios para cashback real
Confirmar API e escopos de clientes/pedidos, consentimento de participantes,
webhooks autenticados e pagamentos efetivos, autorização no checkout,
tratamento de reembolsos, fiscal/ERP e LGPD. Nenhum desses itens é resolvido
por esta agregação.
