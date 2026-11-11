# OAuth Nuvemshop — instalação segura e prévia real em leitura

**Estado:** PR #10 — implementação em branch isolada. Não é uma implantação publicada, nem uma app aprovada na Loja de Aplicativos. Cashback, importação e gravações externas permanecem **desativados**.

## Decisão de produto
O Fideliza só pode utilizar dados de uma loja depois que seu proprietário/administrador autorizar explicitamente o aplicativo. Para esta fase piloto, o usuário já precisa ter conta e associação à loja no Fideliza; **a instalação é iniciada pelo painel**, não pelo app store de forma anônima.

**Permissão exclusiva:** read_products, configurada no Partners Portal. Pedidos, clientes, preços, estoque, descontos, scripts e escrita de catálogo **não são solicitados**.

## Fluxo
1. Owner/admin autenticado abre **Conciliação** e seleciona **Autorizar minha loja**. O frontend solicita POST /api/v1/tenants/{tenant_id}/nuvemshop/connect/ com CSRF de sessão.
2. Backend verifica role e tenant, hostname HTTPS idêntico ao callback cadastrado, configuração e intervalo mínimo entre tentativas.
3. Cria state aleatório de 32 bytes, guarda somente seu SHA-256 com vínculo a sessão, usuário, tenant e app ID, expirando em **cinco minutos**.
4. Navegador vai para https://www.tiendanube.com/apps/{client_id}/authorize?state={nonce}; a Nuvemshop apresenta as permissões do aplicativo.
5. Callback HTTPS em /api/v1/oauth/nuvemshop/callback/ verifica state, sessão, usuário, prazo e role, e consome a tentativa em transação **antes** da chamada externa. Em seguida troca code por token via POST fixo ao endpoint oficial.
6. Valida token_type=bearer, escopo concedido igual a read_products, user_id da resposta como ID da loja e eventual store_id consistente.
7. Confere exclusividade da loja por tenant e por par app/loja. Armazena **somente token cifrado Fernet** no banco, com chave carregada de secret manager. O token nunca aparece na URL de retorno, JSON ou interface.
8. Redirect 303 para /?nuvemshop=connected (ou failed) sem code/state. O painel lê o status por GET protegido.

## APIs
- GET /api/v1/tenants/{id}/nuvemshop/status/ — configurado, conectado, loja e escopo **sem token**; qualquer membro do tenant.
- POST /api/v1/tenants/{id}/nuvemshop/connect/ — inicia autorização; apenas proprietário/administrador, exige HTTPS, CSRF e sessão.
- GET /api/v1/oauth/nuvemshop/callback/ — callback de autorização; state de uso único e sessão original, retorno sem segredos.
- GET /api/v1/tenants/{id}/nuvemshop/catalog/preview/?page=1 — servidor usa token cifrado da instalação do tenant, faz GET oficial de **três produtos** (máximo 50 variantes por prévia) e aplica o motor de conciliação sem writes. Usuário não pode fornecer store_id/token de outra loja.

Limite de taxa: mínimo 15 segundos entre leituras ao vivo por tenant, usando Django cache/Redis no staging. Respeitar headers Retry-After e limites globais da Nuvemshop será obrigatório antes de sincronização contínua.

## Segredos e configuração em Coolify
Inserir **exclusivamente na API** como Environment Variables protegidas, não em código, git, logs ou frontend:

| Chave | Descrição |
| --- | --- |
| NUVEMSHOP_CLIENT_ID | App ID numérico criado no Partners Portal |
| NUVEMSHOP_CLIENT_SECRET | Segredo da aplicação OAuth |
| NUVEMSHOP_TOKEN_KEYS | Chave(s) Fernet base64; primeira criptografa, demais só descriptografam para rotação |
| NUVEMSHOP_OAUTH_CALLBACK_URL | URL HTTPS exata: https://SEU-DOMINIO/api/v1/oauth/nuvemshop/callback/ |
| NUVEMSHOP_API_USER_AGENT | Vidalys Fideliza (contato técnico próprio) |

Gerar uma **nova chave Fernet fora do chat** em terminal seguro:
\`\`\`bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
\`\`\`

A saída é um segredo de produção/homologação. Guardar em secret manager/backup seguro, nunca colar na conversa. Não usar a mesma chave de outras aplicações. Perda da chave impede decifrar tokens; faça backup da chave independente do banco.

Todas as variáveis são opcionais para o app subir: **sem configuração, a UI informa indisponível e bloqueia autorização**, em vez de usar credenciais de exemplo. O Django usa credenciais sintéticas somente nos testes automatizados, em banco descartável.

### Configuração Nuvemshop
- Criar aplicativo parceiro oficial e configurar somente \`read_products\`.
- URL de callback idêntica à variável HTTPS acima; URL do painel e política de privacidade da app devem ser próprias.
- Configurar os três privacy webhooks exigidos (store redact, customer redact, customer data request) e política de privacidade antes de publicar a app na Loja.
- O fluxo atual inicia pelo painel do Fideliza com sessão autenticada. Não atende instalações iniciadas diretamente no Marketplace sem state/sessão; desenvolver onboarding próprio antes da publicação pública.

### Infraestrutura e logs
- O Coolify deve fornecer HTTPS confiável, origem autorizada, rede privada e PostgreSQL com backup/recovery testado antes de migrations.
- O callback não escreve code na URL final. O Nginx não registra o endpoint de callback (access_log off) e o Gunicorn usa somente path, sem query string, no access log.
- O proxy de borda do Coolify também deve ocultar/remover query strings desse endpoint; verificar logs reais em staging antes de liberar OAuth.
- O API service recebe segredos OAuth; o worker não os herda. Não expor Redis/PostgreSQL para a internet.
- Nunca exibir resposta bruta de troca de token nem capturar credenciais em ferramenta de observabilidade.
- Em caso de reinstalação no mesmo app/loja o token anterior pode tornar-se inválido; substituir apenas o registro correspondente, sob transação.
- Tratamento de desinstalação/revogação e privacy webhooks ainda é requisito de produto; **não considerar app pronta para distribuição**.

## Gate de segurança e QA
- Testes de config, chave inválida, criptografia e rotação de chave, token sem plaintext em banco.
- Negar falta de CSRF/HTTPS, analista iniciando OAuth, tenant alheio ou callback sem sessão.
- State expira em cinco minutos, é SHA-256 no banco, consumido somente uma vez (replay bloqueado).
- Token somente para loja retornada por user_id, scope exato read_products, store_id diferente bloqueado e mesma loja não se vincula a dois tenants.
- API de amostra GET não faz INSERT/UPDATE/DELETE, respeita limites e não retorna token. Fonte indicada como nuvemshop_live_read_only.
- Playwright em 390/768/1440 px, sem overflow, com resposta simulada **apenas nos testes**.
- CI Backend, frontend, Docker, Compose externo e visual totalmente aprovados antes de considerar merge.

## Fonte oficial confirmada em 11/11/2026
- https://tiendanube.github.io/api-documentation/authentication
- https://nuvemshop.dev/docs-api/authentication
- https://tiendanube.github.io/api-documentation/resources/product
- https://tiendanube.github.io/api-documentation/resources/product-variant
- https://nuvemshop.dev/apps/publish/guidelines

## Não incluído
- Nenhum token real configurado ou conectado;
- Nenhuma leitura de catálogo Bibelô pelo aplicativo Vidalys;
- Nenhuma importação ou edição de produto, variante, pedido, estoque, preço, cupom ou crédito;
- Nenhum webhook comercial/de privacidade em produção;
- Nenhum deploy para Coolify (somente testes CI de Compose).
