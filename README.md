# Vidalys Fideliza — SaaS de fidelidade e cashback

Produto independente do Vidalys Flow, inicialmente para Nuvemshop. A Bibelô será a primeira loja-piloto após validação e autorização. **Neste momento é uma fundação técnica mais protótipo visual; não existe cashback, pontos ou integração Nuvemshop em funcionamento.**

## Stack
- Backend: Python 3.12, Django 5.2 LTS, DRF, PostgreSQL, Redis e Celery.
- Dependências Python: uv 0.10.0 com backend/pyproject.toml e backend/uv.lock versionados.
- Frontend: React, TypeScript e Vite com tokens Vidalys; telas ilustrativas (dados fictícios).
- Homologação: Docker Compose isolado, preparado para adaptação ao Coolify.
- Qualidade: CI com testes backend, build do frontend e smoke test da stack Docker.

## Comece pelo uv
1. Instale Python 3.12 e uv seguindo a documentação oficial Astral.
2. Entre na pasta backend.
3. Execute: uv sync --locked --python 3.12
4. O uv cria backend/.venv. Não inclua essa pasta no Git.
5. Configure DJANGO_DEBUG=1 e use uv run --locked python manage.py migrate e uv run --locked python manage.py test.
6. Execute uv run --locked python manage.py runserver.

Atenção: sem DB_HOST e DATABASE_URL e com DEBUG=1, a base local de desenvolvimento será SQLite. Homologação e produção usam PostgreSQL.

## Executar a stack por Docker Compose
1. Na raiz, copie .env.example para .env.
2. Substitua TODOS os placeholders por senhas e chaves fortes. Nunca versione o .env.
3. Execute docker compose config para validar o arquivo.
4. Execute docker compose up -d --build.
5. Abra http://127.0.0.1:8080 e http://127.0.0.1:8080/api/health/.

O servidor frontend escuta apenas na interface local em 127.0.0.1; o tráfego externo para homologação deve usar o proxy HTTPS do Coolify e uma configuração de rede revisada.

## Identidade visual P0
A experiência do lojista usa grafite #0B1120, azul #1263FF e ciano #00D1E6 como acento. Telas para consumidor usam a marca da loja; protótipos precisam de aprovação em 390/768/1440px e WCAG AA. O Django Admin não é interface comercial.

## Documentação
Leia AGENTS.md e docs/01-PRD.md até docs/08-UX-UI-CRITERIOS.md. Instruções de execução estão em docs/09-UV-EXECUCAO-COOLIFY.md. Handoff inicial: codex/PRIMEIRA_TAREFA.md.

Notion (hub privado): https://app.notion.com/p/4148f612deaf8143b7d2c27f0623fa61

## Restrições
Não conectar produção Nuvemshop, alterar tema Ipanema, instalar scripts, ativar cashback ou editar produtos/pedidos neste estágio. Credenciais e dados pessoais nunca vão ao GitHub.


## Portal do lojista — etapa atual
A rota / usa autenticação de sessão Django, com proteção CSRF e isolamento por associação a lojas. A rota /demo contém apenas exemplos ilustrativos sem API comercial. A calculadora da área autenticada chama a API por tenant; não cria ou concede cashback. Consulte docs/11-PORTAL-LOJISTA-ACESSO.md para provisionamento de usuários/lojas no staging, configurações seguras e limitações.

## Homologação no Coolify
Use `compose.coolify.yaml` e [o plano de homologação](docs/12-HOMOLOGACAO-COOLIFY.md).
A configuração remove portas fixas, separa volumes, limita recursos e exige HTTPS.
O recurso deve permanecer parado, sem domínio e sem deploy automático durante a
preparação; os gates e limitações estão registrados no plano.
