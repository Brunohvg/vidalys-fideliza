# Começar com Codex — Vidalys Fideliza

**Arquivo de entrada principal.** Leia `AGENTS.md` e todos os documentos de `docs/` e ativos de `brand/` antes de implementar. Fonte editorial atual: https://app.notion.com/p/4148f612deaf8143b7d2c27f0623fa61 (se disponível).

## O que fazer na PRIMEIRA tarefa
1. Inspecionar a estrutura e o status de Git do repositório; resumir requisitos, decisões tomadas e dúvidas críticas.
2. Verificar documentação oficial atual da Nuvemshop para OAuth, scopes, webhooks, Nube SDK e Discount API; registrar limitações reais e plano de PoC (sem tocar em produção).
3. Definir mapa de navegação, wireframes e protótipos de alta fidelidade para dashboard, regras e carteira mobile. O visual premium é **prioridade P0**: nunca entregar Django Admin ou uma UI genérica como tela de produto. Usar a identidade `docs/05-IDENTIDADE.md` e critérios `docs/08-UX-UI-CRITERIOS.md`.
4. Propor estrutura modular Django/DRF + PostgreSQL + Redis/Celery + frontend TypeScript, isolamento multi-tenant e testes. Se a tarefa for de implementação, iniciar SOMENTE a fundação local da Fase 1 após preflight e escopo de mudança.
5. Entregar evidência: arquivos alterados, comandos executados, testes, screenshots reais caso haja UI, bloqueios e próximo PR recomendado.

## Proibido sem autorização
Instalar aplicativo na Bibelô, ativar cashback real, consumir crédito de clientes, usar credenciais reais, publicar em produção, alterar produto/pedido/estoque, editar tema Ipanema ou mexer no Vidalys Flow.

## Pronto significa
Contratos não inventados, histórico versionado, aplicação testável, UX visual comprovada (quando houver UI) e todas as limitações registradas. Priorize alterações pequenas, revisáveis, com rollback.
