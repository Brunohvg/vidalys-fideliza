# 45 — Auditoria de variáveis após a consolidação do Compose

O único arquivo Docker Compose da aplicação é compose.yaml.
O template da configuração é .env.example. Não criar outro compose por ambiente.
Os valores reais do Coolify NÃO foram inspecionados e não são conhecidos.

## Variáveis essenciais do Coolify para API e worker
- DATABASE_URL: URI PostgreSQL privado externo. Substitui todos os DB_*.
- DJANGO_SECRET_KEY: mesma chave forte para API e worker.
- DJANGO_ALLOWED_HOSTS: hostname público e hosts necessários.
- DJANGO_CSRF_TRUSTED_ORIGINS: origem HTTPS pública.
- REDIS_URL e CELERY_BROKER_URL: definidos dentro do Compose; não cadastrar à mão.
- DJANGO_DEBUG=0 e DJANGO_SECURE_SSL_REDIRECT=1: fixos no Compose.

## Nuvemshop — apenas API
- NUVEMSHOP_CLIENT_ID: identificador do app.
- NUVEMSHOP_CLIENT_SECRET: assinatura de webhooks e OAuth.
- NUVEMSHOP_TOKEN_KEYS: chave(s) Fernet para guardar token OAuth cifrado.
- NUVEMSHOP_OAUTH_CALLBACK_URL: callback HTTPS oficial.
- NUVEMSHOP_API_USER_AGENT: agente requerido na API.

Essas cinco variáveis têm papéis diferentes. Não reutilizar client_secret
como token nem misturar os IDs de cliente com os da loja. A conexão só
funciona com contrato completo e OAuth da própria loja piloto.

## SMTP2GO — worker e gate separado
- EMAIL_HOST: host do servidor (ex.: mail.smtp2go.com).
- EMAIL_HOST_USER: usuário autenticado.
- EMAIL_HOST_PASSWORD: segredo autenticado.
- DEFAULT_FROM_EMAIL: remetente autorizado (ex.: Vidalys <contato@vidalys.com.br>).
- FIDELIZA_PUBLIC_BASE_URL: host HTTPS público, na API e no worker.
- FIDELIZA_EMAIL_DELIVERY_ENABLED: gate em API e worker, desligado por padrão.

EMAIL_BACKEND está fixado no Compose para SMTP; EMAIL_PORT=587,
EMAIL_USE_TLS=1 e EMAIL_USE_SSL=0 ficam fixos para a infraestrutura
SMTP2GO adotada. SERVER_EMAIL herda DEFAULT_FROM_EMAIL.
Portanto NÃO precisam de configurações separadas no painel do Coolify.
Para mudar provedor/transporte, alterar o contrato e os testes antes de
migração; não alterar silenciosamente valores já utilizados em produção.

## Recursos opcionais, todos desligados por padrão
- FIDELIZA_PUBLIC_SIGNUP_ENABLED (clientes que participam do clube)
- FIDELIZA_MERCHANT_SIGNUP_ENABLED (novos lojistas, API somente)
- FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED
- FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED
- FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED
- FIDELIZA_PARTICIPANT_APPROVAL_ENABLED
- FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED

Cada gate controla uma capacidade distinta; somente ativar após o
piloto verificar OAuth, LGPD, SMTP, tenant e casos sintéticos. Flags OFF
não precisam existir no painel. Nenhum gate ativa saldo: o código força
FIDELIZA_LEDGER_WRITES_ENABLED=False.

## Nomes legados dispensáveis
- FIDELIZA_DATABASE_URL, FIDELIZA_DJANGO_SECRET_KEY,
  FIDELIZA_DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
- POSTGRES_PASSWORD, POSTGRES_USER, POSTGRES_DB: só banco legado embutido.
- SERVICE_PASSWORD_64_DJANGO, FIDELIZA_HOMOLOG_LOGIN_PASSWORD,
  FIDELIZA_TEST_ADMIN_PASSWORD, FIDELIZA_STAGING_HOST, FRONTEND_PORT.
- EMAIL_BACKEND, EMAIL_PORT, EMAIL_USE_TLS, EMAIL_USE_SSL e SERVER_EMAIL
  já estão explicitados/derivados no Compose e não precisam de entrada.

Atualização de segurança: o modo Managed não isolou os segredos na
homologação real. O Compose agora exige Raw, sem sobrescritas vazias,
para impedir a injeção global de env_file. A auditoria reporta quais NOMES legados ainda aparecem,
sem revelar valores. Não apagar nenhuma variável do painel antes de
confirmar o recurso, backup, SHA efetivo e ausência de consumidores
externos. Esses nomes podem existir legitimamente em outros projetos.

## Verificação
- GitHub CI: backend, frontend, visual, Docker e banco externo.
- API: python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
- Worker: python scripts/audit_smtp_env.py --host fideliza-homolog.optarys.com.br
- CI isolado: python .github/scripts/check_coolify_env_isolation.py
- Ler docs/43-ROADMAP-TESTES-E-PENDENCIAS-SEM-PULAR-ETAPAS.md.

Pendente: checar os nomes presentes de fato no recurso Coolify, mudar
Compose Location para compose.yaml e validar migrações, OAuth real, SMTP
real, consentimento, HMAC e pedidos com loja de testes. Nenhum deploy
nem operação financeira realizada nesta entrega.


Obrigatória no Raw: FIDELIZA_DB_NETWORK (rede Docker existente do
PostgreSQL externo). Opcional: FIDELIZA_PROXY_NETWORK (default coolify).
Confirmar Traefik/rotas e backup antes de trocar modo e implantar.


## Acesso do lojista sem Nuvemshop

A autenticação de comerciantes funciona por e-mail após confirmação. O controle `FIDELIZA_MERCHANT_SIGNUP_ENABLED` só habilita o cadastro de comerciantes e nunca abre o cadastro de clientes. Reutiliza `FIDELIZA_EMAIL_DELIVERY_ENABLED` e a mesma fila SMTP restrita ao worker; não criar novas credenciais SMTP. O app Nuvemshop é opcional, nunca bloqueia login, tenant ou simulação sem escrita financeira. Django Admin permanece separado em `/admin/` e só aceita staff com permissão.
