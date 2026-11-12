# 44 — Contrato único do Docker Compose Vidalys Fideliza

## Decisão
A homologação passa a ter um único arquivo de aplicação: compose.yaml.
Contém Redis, Django API, Celery worker e frontend. Não contém PostgreSQL,
que continua como recurso independente e privado no Coolify.

Foram aposentados do repositório os arquivos Compose anteriores com banco
embutido, Compose externo duplicado e override YAML dos testes. O Git
preserva o histórico, mas o Coolify não muda sua configuração automaticamente.

## Segurança
Nenhuma porta publicada; Nuvemshop OAuth apenas na API, SMTP no worker,
PostgreSQL e segredo Django na API+worker, frontend e Redis sem segredos.
O teste de isolamento reproduz a injeção de env_file pelo Coolify. Flags
de privacidade, associação automática, pedidos e cashback ficam fechadas
por padrão. Banco e volumes existentes não devem ser recriados.

## Migração na homologação
1. Identificar o recurso correto e SHA realmente publicado; backup privado
   do PostgreSQL e teste da restauração antes de atualizar stack.
2. Alterar o campo Compose Location da Application Git para compose.yaml.
3. No destino privado fideliza-homolog, habilitar Connect to predefined network
   exclusivamente no destino do PostgreSQL, nunca no compartilhado coolify.
4. Comparar DATABASE_URL, DJANGO_SECRET_KEY, callback OAuth e SMTP com as
   configurações existentes (somente presença e validade, sem copiar segredos).
5. Conferir Deployable Compose gerado, escopo de variáveis, saúde dos quatro
   serviços, HTTPS e processo Celery; não habilitar flags por conveniência.
6. Migrar somente após CI verde no SHA final. Não alterar main ou Bibelô.

## CI sem YAML adicional
Os seis jobs permanecem: backend, frontend, visual QA, docker smoke,
Coolify smoke e banco externo smoke. O script de CI com Python inicia
um PostgreSQL 16 independente descartável no Docker e o conecta à rede
temporária do Compose da aplicação. O script exige GITHUB_ACTIONS=true
e remove os recursos efêmeros. Não toca nenhum banco hospedado.

.env.example é apenas modelo; segredos devem ficar no Coolify.
Script de isolamento: .github/scripts/check_coolify_env_isolation.py.
Diagnóstico API: python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
Diagnóstico SMTP: python scripts/audit_smtp_env.py --host fideliza-homolog.optarys.com.br
Continuar roadmap: docs/43-ROADMAP-TESTES-E-PENDENCIAS-SEM-PULAR-ETAPAS.md
