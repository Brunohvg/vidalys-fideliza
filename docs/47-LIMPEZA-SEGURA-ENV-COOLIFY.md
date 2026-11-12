# 47 — Limpeza segura da env do Coolify

Fonte: inventario compartilhado manualmente. Nenhum valor de segredo foi
copiado para este documento. O ambiente em execucao NAO foi acessado.

O arquivo de configuracao da aplicacao e somente compose.yaml.
O modelo enxuto esta em .env.example (nao e uma env pronta para colar
com placeholders).

MANTER: DJANGO_SECRET_KEY, DATABASE_URL, DJANGO_ALLOWED_HOSTS,
DJANGO_CSRF_TRUSTED_ORIGINS, FIDELIZA_PUBLIC_BASE_URL.

REMOVER DO PAINEL SOMENTE APOS VERIFICAR QUE NENHUM SERVICO EXTERNO USA:
FIDELIZA_HOMOLOG_LOGIN_PASSWORD, SERVICE_PASSWORD_64_DJANGO,
FIDELIZA_DJANGO_SECRET_KEY, FIDELIZA_STAGING_HOST,
FIDELIZA_DATABASE_URL, FIDELIZA_TEST_ADMIN_PASSWORD,
FIDELIZA_DB_PASSWORD. Valores que representavam senhas expostas
devem ser invalidados/rotacionados, nao apenas apagados.

NAO PRECISAM DE ENTRADA: EMAIL_BACKEND, EMAIL_PORT,
EMAIL_USE_TLS, EMAIL_USE_SSL e SERVER_EMAIL: estao definidos ou
derivados no Compose. REDIS_URL, CELERY_BROKER_URL,
DJANGO_DEBUG e HTTPS tambem sao definidos no Compose.
Nao adicionar FIDELIZA_LEDGER_WRITES_ENABLED.

FLAGS INATIVAS: FIDELIZA_PUBLIC_SIGNUP_ENABLED,
FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED,
FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED,
FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED,
FIDELIZA_PARTICIPANT_APPROVAL_ENABLED,
FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED,
FIDELIZA_EMAIL_DELIVERY_ENABLED. Todos possuem default 0 no Compose.
Entradas vazias ou zero sao redundantes na homologacao atual.

NUVEMSHOP: as cinco variaveis NUVEMSHOP_CLIENT_ID,
NUVEMSHOP_CLIENT_SECRET, NUVEMSHOP_TOKEN_KEYS,
NUVEMSHOP_OAUTH_CALLBACK_URL, NUVEMSHOP_API_USER_AGENT
estao vazias no inventario. Nao inserir valores ficticios nem
conectar parcialmente. Precisam ser configuradas juntas no piloto.

SMTP2GO: EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD,
DEFAULT_FROM_EMAIL; manter desativado ate validar credenciais,
remetente e envio no worker. FIDELIZA_PUBLIC_BASE_URL e compartilhada.

ROTACAO SEGURA:
1. Confirmar Application homolog, branch, SHA, Compose Location e banco.
2. Validar backup/restauracao antes de qualquer ajuste na DATABASE_URL.
3. Trocar senha exposta no proprio PostgreSQL e atualizar DATABASE_URL
   de forma coordenada. Trocar so a string quebra conexao.
4. Revogar senhas antigas e mudar DJANGO_SECRET_KEY. Uma troca de chave
   pode encerrar sessoes e invalidar links de email assinados.
5. Organizar as variaveis do Coolify, mantendo as obrigatorias.
   A Developer view remove entradas omitidas ao salvar; antes de usar,
   guardar a configuracao correta em cofre privado.
6. Reiniciar/reimplantar, conferir healthcheck, Redis, Celery e migracoes.
   Rodar auditoria na API e posteriormente teste SMTP no worker.

API: python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
Worker: python scripts/audit_smtp_env.py --host fideliza-homolog.optarys.com.br

Documentacao Coolify:
https://coolify.io/docs/applications/configuration/environment-variables
https://coolify.io/docs/applications/builds/docker-compose

Segredos no chat devem ser tratados como comprometidos; apagar mensagem
nao os invalida. Nao mexer em main, Bibelo, banco ou variaveis de producao.
