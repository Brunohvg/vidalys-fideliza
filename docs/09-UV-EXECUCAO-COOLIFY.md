# Desenvolvimento local, uv e Compose único

## Local — sem alterar Coolify
Instale Python 3.12, uv 0.10.0 e Node.js 22. Configure
DJANGO_DEBUG=1 no ambiente de desenvolvimento e remova DATABASE_URL
e DB_HOST para usar o SQLite local. Execute:

1. cd backend
2. uv sync --locked --python 3.12
3. uv run --locked python manage.py migrate
4. uv run --locked python manage.py check
5. uv run --locked pytest -q
6. uv run --locked python manage.py runserver

No frontend: npm install e npm run dev. Banco local não substitui
migrações/testes do PostgreSQL externo de homologação.

## Docker / Coolify
Somente compose.yaml contém a stack do Fideliza: api, worker, redis e
frontend. O banco PostgreSQL é recurso privado separado. Não existem
portas públicas fixas no Compose. Para implantar, selecionar a rede
privada do banco e permitir conexão ao destino predefinido somente lá.

Não executar docker compose up sem um PostgreSQL externo e as variáveis
da Application devidamente preparadas. Não é uma stack de desenvolvimento
com banco embutido. O template .env.example não tem credenciais reais.

## CI
Os seis jobs incluem backend, frontend, QA visual e três smoke tests
com o MESMO compose.yaml. O script .github/scripts/ci_single_compose.py
inicia PostgreSQL separado descartável no runner CI, sem arquivo de
override Compose e sem contato com Coolify.

Segurança: HTTPS, CSRF, sessão Secure, dados isolados por loja;
sem tokens, clientes ou cashback real.

Continuidade: docs/43, docs/44 e docs/45.
