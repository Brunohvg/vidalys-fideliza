# Execução do projeto com uv e Coolify

**Etapa atual:** scaffold executável e protótipo visual React, SEM conexão Nuvemshop, SEM carteira financeira e SEM descontos reais.

## Como o uv funciona
O backend usa backend/pyproject.toml e Python 3.12. O comando uv sync instala dependências e cria automaticamente backend/.venv. A pasta .venv é local, nunca entra no Git. O arquivo uv.lock é versionado para fixar versões e tornar as instalações previsíveis. O CI gera o primeiro uv.lock no GitHub Actions; após isso, executar uv sync --locked e manter lock atualizado quando dependências mudarem.

## Rodar em desenvolvimento
Requisitos: uv, Python 3.12, Node.js 22 (ou Docker).
1. Copie .env.example para .env na raiz e substitua os valores de exemplo. Nunca faça commit de segredos.
2. Entre em backend e rode uv sync --python 3.12.
3. Para desenvolvimento sem PostgreSQL, configure DJANGO_DEBUG=1 e DATABASE_URL=sqlite:///:memory: apenas para check; para persistência local use DJANGO_DEBUG=1 sem DB_HOST/DATABASE_URL e o Django criará local.sqlite3.
4. Rode uv run python manage.py migrate.
5. Rode uv run python manage.py check e uv run pytest.
6. Rode uv run python manage.py runserver (URL local /api/health/).
7. Em outro terminal, entre em frontend e execute npm install e npm run dev.

Observação: o frontend é um protótipo visual com dados declaradamente fictícios. Ele não autentica usuários nem controla cashback.

## Docker Compose (homologação isolada)
Na raiz:
1. cp .env.example .env e substitua senhas/chaves por valores fortes.
2. docker compose config.
3. docker compose up --build -d.
4. Verifique http://localhost:8080 e http://localhost:8080/api/health/.
5. docker compose logs -f api e docker compose logs -f frontend.

O frontend publica apenas em 127.0.0.1:8080; db, redis e api não publicam portas. Para Coolify, substituir publicação local por roteamento HTTPS via proxy do Coolify depois de verificar suas redes e configuração de domínio. NÃO expor PostgreSQL ou Redis na internet.

## O que ainda deve ser validado antes do Coolify
- Construção de ambas as imagens Docker em servidor com acesso a imagens e índices de pacotes.
- Banco persistente, backup e restauração; não compartilhar banco com Vidalys Flow.
- Serviço web acessível por domínio de homologação, com HTTPS e headers corretos de proxy.
- Variáveis DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS e DJANGO_SECURE_SSL_REDIRECT conforme TLS.
- uv.lock gerado e CI verde; migrações controladas; testagem ponta a ponta de /api/ready/.
- Política de acesso de staging: autenticação ou restrição de tráfego; não publicar como aplicativo comercial.

## Segurança
Nunca incluir token OAuth, credencial Coolify, chave real, senha, dump do banco ou .env no repositório. O projeto não altera o tema Ipanema, estoque, pedidos ou descontos reais.

## Critérios de aceite técnico
CI executa uv sync e valida check/makemigrations/pytest; frontend executa npm run build. Esses resultados validam o build básico e testes automatizados, NÃO demonstram checkout, deploy real ou geração de cashback.
