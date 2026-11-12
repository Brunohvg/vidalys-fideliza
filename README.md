# Vidalys Fideliza — SaaS de fidelidade e cashback com controle de margem

Plataforma multitenant independente do Vidalys Flow, com integração inicial
à Nuvemshop. A loja Bibelô só poderá entrar num piloto após validação e
autorização. Não existe cashback financeiro, pontos, cupons nem resgate real.

## Implementado na branch homolog
- Portal do lojista versão v2 (navy, jade, mint e dourado).
- Login seguro, preferências, rascunhos de campanhas e participantes.
- OAuth Nuvemshop e prévias GET de catálogo, clientes e pedidos, sob flags.
- Inbox HMAC idempotente de pedidos e conferência atual somente leitura.
- Carteira/ledger interno sem concessão real; motor de benefícios só simula
  objetivos e orçamento sobre dados hipotéticos.
- Não estão ativos: missões, níveis VIP, indicação, conciliação financeira,
  cashback, resgate ou integrações com PDV e WhatsApp.

## Único Docker Compose
O repositório usa somente compose.yaml (API Django, Celery worker, Redis e
frontend React/Nginx). O PostgreSQL 16 é um recurso PRIVADO e EXTERNO à
stack no Coolify. Não há portas publicadas na aplicação.

Configurar a Application Git para Compose Location compose.yaml somente
após conferir backup/restauração, network privada do PostgreSQL, SHA e
segredos existentes. O Git não altera automaticamente a Application Coolify.
O arquivo .env.example é modelo; nunca levar secrets ao Git.

## Desenvolvimento local
Requisitos: Python 3.12, uv 0.10.0 e Node.js 22.
Django com DJANGO_DEBUG=1 e sem DATABASE_URL/DB_HOST usa SQLite local.

    cd backend
    uv sync --locked --python 3.12
    uv run --locked python manage.py migrate
    uv run --locked pytest -q
    uv run --locked python manage.py runserver

Frontend: cd frontend; npm install; npm run dev.

Para CI Docker, .github/scripts/ci_single_compose.py inicializa PostgreSQL
efêmero fora da stack, executa smoke tests e remove tudo. Não executar no
Coolify: o script requer GITHUB_ACTIONS=true. O CI verde não demonstra
que a mesma versão foi implantada na hospedagem.

## Segurança
NUVEMSHOP_CLIENT_SECRET, tokens e chaves ficam somente na API.
Usuário/senha SMTP ficam somente no worker. Redis e frontend não recebem
segredos. FIDELIZA_LEDGER_WRITES_ENABLED é fixamente False no código.
Sem alterações automáticas na main, produção ou Nuvemshop da Bibelô.

## Próximo passo sem perder histórico
- docs/43-ROADMAP-TESTES-E-PENDENCIAS-SEM-PULAR-ETAPAS.md
- docs/44-STACK-COMPOSE-UNICO.md
- docs/45-CHECKLIST-VARIAVEIS-E-REDUNDANCIAS.md
- docs/42-MOTOR-DE-BENEFICIOS-SIMULACAO.md
- docs/35-ARQUITETURA-MULTICANAL-E-TESTE-PONTA-A-PONTA.md
- AGENTS.md

Notion: https://app.notion.com/p/4168f612deaf813393bdc30e1d79d2f5
