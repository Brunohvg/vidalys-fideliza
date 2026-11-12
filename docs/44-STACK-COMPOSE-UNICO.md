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
A auditoria real reprovou o Managed do Coolify por herdar segredos globalmente. O único Compose agora exige Raw, sem x-block-inherited-credentials; o teste executa a configuração Raw e um controle negativo que denuncia a injeção do Managed. Flags
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


## Redução de variáveis operacionais

As variáveis SMTP constantes ficaram fixas no único Compose e
SERVER_EMAIL passou a herdar DEFAULT_FROM_EMAIL. O inventário de
obrigatórias, opcionais, flags e nomes legados está no documento 45.
Nada foi apagado do painel autenticado do Coolify.


## Mudança obrigatória após auditoria real — 12/11/2026

No recurso `fideliza-homologacao-dbexterno`, o modo Managed gerou
ambiente SMTP em API/frontend/Redis, além de credenciais de banco e
Django em frontend/Redis. O Compose fonte tinha uma lista de 50
sobrescritas vazias que o Coolify reinterpretava, mantendo variáveis
legadas presas no painel. Essa estratégia foi removida.

**Aplicar somente RAW:** Application > Advanced > Docker compose >
Compose deployment > Raw (deploy file as-is). Não usar o modo Managed.

O único `compose.yaml` agora contém rede app interna, rede database
externa somente para API/worker, rede proxy externa somente para
frontend, roteadores HTTP/HTTPS Traefik, TLS com certresolver letsencrypt
e nenhum host port público. Redis não tem env e frontend não recebe
segredos. A rede do DB **não é criada pelo Compose**.

**Antes de deploy:** identificar a rede Docker existente do banco
PostgreSQL externo e preencher FIDELIZA_DB_NETWORK; conferir se proxy
real é Traefik, rede proxy (default coolify), entrypoints http/https e
resolver letsencrypt. Se diferente, interromper e adaptar a configuração.
Confirmar backup com restauração do DB e que o SHA do CI está aprovado.
O modo Raw não cria automaticamente rotas e redes do Coolify; sem essas
conferências, o site ou a conexão DB podem ficar indisponíveis.

Depois da troca de modo e recarga da definição no painel, conferir
Compose gerado e escopo de secrets sem mostrar valores. A lista vazia
removida permite excluir entradas legadas do Coolify, **somente** após
confirmar ausência de outros consumidores. Rotacionar as credenciais
que foram expostas, de forma coordenada com o banco, separadamente.

CI: testar Compose Raw sem env_file, incluir controle negativo que
simula env_file compartilhado do Managed (precisa detectar vazamentos),
e inspecionar env dos quatro contêineres reais. CI verde não é evidência
de deploy no Coolify.

Referências oficiais:
https://coolify.io/docs/applications/builds/docker-compose
https://github.com/coollabsio/coolify/issues/8219
