# Prompt inicial para colar no Codex

Estamos iniciando o **Vidalys Fideliza**, novo SaaS multi-tenant de fidelidade/cashback para Nuvemshop, independente do Vidalys Flow. Use o repositório aberto como fonte de verdade e leia obrigatoriamente `AGENTS.md`, `README.md`, `codex/CODEX_START.md`, todos os `docs/` e os arquivos `brand/`. A documentação editorial mais nova está no Notion: https://app.notion.com/p/4148f612deaf8143b7d2c27f0623fa61 (se a conexão estiver disponível; caso contrário, use os arquivos e registre a limitação).

**Esta primeira tarefa é de descoberta e planejamento verificável — NÃO implemente o sistema completo ainda.**

1. Inspecione os arquivos, descreva a arquitetura proposta e conflitos ou lacunas.
2. Confira as documentações oficiais atuais da Nuvemshop (OAuth, permissões, webhooks, Nube SDK, Discount API) e informe o que depende de prova de conceito no checkout.
3. Estruture um plano de execução em pequenos PRs para a Fase 0, Design P0 e a fundação da Fase 1.
4. Trate **QUALIDADE VISUAL COMO P0**: proponha telas e fluxos; crie wireframes/protótipos iniciais de alta fidelidade para o painel do lojista, a carteira do cliente e a página de regras, seguindo a identidade Vidalys. Não aceite layout genérico nem Django Admin como produto final. Valide o futuro design em 390/768/1440 px, com estados e contraste AA.
5. Proponha a árvore de pastas Django/DRF, React/TypeScript, PostgreSQL, Redis/Celery, testes, segurança, segregação de tenants e integração Nuvemshop sem ainda conectar a loja.
6. Entregue resumo executivo, decisões para aprovação, limitações, arquivos propostos, telas de referência, plano de testes e **o escopo do primeiro PR**, para minha aprovação antes de alterar produção ou serviços externos.

Restrições: não conectar produção, não ativar cashback, não criar desconto real, não alterar estoque/pedidos, não editar Ipanema nem Vidalys Flow, não usar tokens reais ou criar endpoints Nuvemshop fictícios. Responda em português do Brasil.
