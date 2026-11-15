# Vidalys Fideliza — SaaS de fidelidade e cashback com controle de margem

Plataforma multitenant independente do Vidalys Flow, com integração inicial
à Nuvemshop. A loja Bibelô só poderá entrar num piloto após validação e
autorização. Não existe cashback financeiro, pontos, cupons nem resgate real.

## Código consolidado para homologação (15/11/2026)

- Portal do lojista v2, participantes e clube público; UX ainda exige
  avaliação humana no ambiente publicado.
- OAuth Nuvemshop, catálogo e pedidos GET, webhooks HMAC, vínculo de
  participante e notificações Celery/SMTP — testes sintéticos aprovados.
- Regras, pontos, cashback, vouchers, reserva/revogação de cupons e
  gate financeiro **implementados, desligados por padrão**.
- Conciliação de itens por SKU/custos verificados e taxas Pagar.me v5
  autenticadas de `payables`, com recibos imutáveis PostgreSQL.
- NubeSDK de checkout em `integrations/nuvemshop/` é **somente fonte de QA**;
  não instalado em nenhuma loja por este projeto.
- **Ainda não homologado:** SHA implantado no Coolify Raw, backup/restauração
  do DB externo, OAuth/SMTP/pedido PSP sandbox real, bloqueio anti-bypass
  no checkout. **GO-LIVE comercial NO-GO**.

Próxima ação única em `docs/43-ROADMAP-TESTES-E-PENDENCIAS-SEM-PULAR-ETAPAS.md`.
Procedimento de teste do clube: `docs/PR30-RELEASE-AND-PILOT-QA.md`.

## Único Docker Compose
O repositório usa somente compose.yaml (API Django, Celery worker, Redis e
frontend React/Nginx). O PostgreSQL 16 é um recurso PRIVADO e EXTERNO à
stack no Coolify. Não há portas publicadas na aplicação.

Configurar a Application Git para Compose Location compose.yaml e modo **Raw** somente
após conferir backup/restauração, rede externa real do PostgreSQL, proxy Traefik, SHA e
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
