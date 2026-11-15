# PR #24 — Runbook de homologação real e critérios GO/NO-GO

**Estado em 14/11/2026 (America/Sao_Paulo): PROCEDIMENTO PREPARADO; NÃO EXECUTADO.**
Fonte: branches do GitHub, scripts versionados e CI sintético.
**Não** há evidência de acesso administrativo ao Coolify nem ao PostgreSQL real
nesta sessão. Não marcar backup, migrate, merge, E2E ou deploy como concluídos.

## 0. Inventário e bloqueios da janela

- Homolog base, observada em 14/11/2026: \`c25d668ec1b668c3a254b816cc96b6236a0dadb2\`.
- CI aprovado do PR #23: commit
  \`2aa3168ca40b361a8095c2345a2c6aae0ebacb3b\`;
  https://github.com/Brunohvg/vidalys-fideliza/actions/runs/43636241277
  (400 testes backend, 192 subtestes, 139 Playwright; PG externo sintético).
- Stacks em draft: #18 → #19 → #20 → #21 → #22 → #23.
  A aprovação do CI **não** aprova merge, restore, execução financeira ou deploy.
- Infra em \`compose.yaml\`: **Coolify Git Compose RAW**, PostgreSQL externo,
  banco privado em rede \`FIDELIZA_DB_NETWORK\`, frontend HTTPS
  \`https://fideliza-homolog.optarys.com.br\`; API e worker internos.
  \`api\` apenas usa \`migrate --check\` ao iniciar; não migra automaticamente.
- SQL do PR #23 tem triggers PostgreSQL sobre points e wallets;
  o aplicativo precisa executar com role de **mínimos privilégios**.
- G7/G8 e pagamentos reais continuam **OFF**: não habilitar
  \`FIDELIZA_POINTS_WRITES_ENABLED\`,
  \`FIDELIZA_LEDGER_WRITES_ENABLED\`,
  \`FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED\` ou adapters PSP confiáveis.
  A API de vouchers com \`reward_id\` deve responder 409 enquanto bloqueada.

**Aprovações distintas necessárias:** (1) owner de dados/loja permite janela e
confirma backup/restore, (2) revisor de código libera a stack, (3) operador
Coolify/Postgres confirma credenciais exclusivamente de homologação, (4)
responsável pela homologação assina o relatório após E2E.

### Preparação operacional obrigatória

1. Desabilitar **auto-deploy do Coolify para homolog**, automações/webhooks de
   deploy e eventuais rotinas GitHub com release automático. NÃO desligar a loja
   Bibelô ou outro app que use o host.
2. Identificar PostgreSQL externo **exato**, nome da base, host, porta e roles;
   validar snapshots de infraestrutura, espaço, versões de client/servidor e
   segredo protegido. Não compartilhar URLs/tokens em PR, logs ou conversa.
3. Agendar manutenção e parar SOMENTE API/worker e outros escritores do Fideliza
   para que **nenhuma transação nova** entre desde o snapshot até o teste de
   recuperação e fim da janela. Conferir sessões abertas e integrações upstream.
4. Pré-provisionar banco privado **vazio**, separado da base original, com nome
   terminado em \`_restorecheck\`; garantir armazenamento externo para dump
   com permissão \`0700\` e acesso restrito. Dump e scratch contêm dados pessoais.
5. Definir responsável do rollback, RPO/RTO aceitáveis, forma de isolar sessões
   e plano de troca da URL caso a base precise ser reconstruída. **Não** usar
   \`DROP DATABASE\`, \`migrate ... zero\` nem restaurar sobre base com escritas.

## 1. Pré-merge: validate-only, sem efeitos

No checkout do **PR #24**, com cliente Python 3.12+ e GitHub token de
leitura autorizado (\`GITHUB_TOKEN\` ou \`GH_TOKEN\`) no shell privado:

\`\`\`bash
python3 scripts/homolog_merge_preflight.py --self-test
python3 scripts/homolog_merge_preflight.py
\`\`\`

O script compara os PRs com branches e SHAs aprovados, exige CI SUCCESS,
\`mergeable\`, ancestry sem divergência e **nenhum draft**.
Neste momento, o resultado esperado é **MERGE_GATE=BLOCKED** porque
#18–#23 continuam draft. Não contornar. Após reviews e autorizações,
convertê-los em Ready for review e repetir a conferência.

**Ordem exata, de baixo para cima:**

| Ordem | PR | Branch | Base original |
|---|---:|---|---|
| 1 | #18 | \`refactor/omnichannel-customer-identity\` | \`homolog\` |
| 2 | #19 | \`feature/pr19-channel-order-ingestion\` | #18 |
| 3 | #20 | \`feature/pr20-loyalty-offline-engine\` | #19 |
| 4 | #21 | \`feature/pr21-frontend-routes-visual-qa\` | #20 |
| 5 | #22 | \`feature/pr22-consolidation-homolog-gates\` | #21 |
| 6 | #23 | \`feature/pr23-compliance-conformance-fixes\` | #22 |

O GitHub suporta stacked PRs e os rebases/re-alvos sucessivos ao mesclar
o PR inferior. **Não executar o comando REST tradicional de merge**
para forçar um stack; usar o fluxo nativo de PRs empilhados do GitHub e
revalidar CI/reviews e base atual a cada passo.
O rebase pode mudar SHAs; atualizar o manifesto de release após revisão
explícita e CI no novo SHA.

**Porta de segurança:** o GitHub pode receber os merges durante a janela
somente se auto-deploy estiver desativado e o banco/worker ainda não tiverem
recebido migrações automáticas. Após cada merge, registrar PR, base, nova HEAD
da \`homolog\`, CI/reviews e hora. Se a stack estiver não linear, resolver
conflitos em PR e reexecutar testes, nunca forçar merge.

PR #24 contém scripts/docs desta janela e é **separado** dos seis merges.
Para utilizar PR #24 sem mesclá-lo antes da homologação, executar seu
checkout pinado e confirmar que as migrações e código de aplicação são
iguais ao resultado acumulado de #23:

\`\`\`bash
git fetch origin
git diff --exit-code origin/homolog HEAD -- \
  backend/apps backend/config frontend/src compose.yaml
\`\`\`

Se houver diferenças, **bloquear**: o código da operação precisa corresponder
ao artefato que será implantado. Para executar ferramentas diretamente em
\`homolog\`, mesclar #24 **somente depois de #23**, com aprovação adicional.

## 2. Backup e migração controlada no PostgreSQL real

**Atenção:** instruções abaixo são para um operador conectado à rede privada
do servidor de homologação. O script não contém segredos e **não** funciona
automaticamente pelo conector GitHub, no CI nem nesta conversa.

No checkout de código **exatamente aprovado**, exportar os valores reais pelo
gerenciador seguro de segredos; nunca colar credenciais em comandos ou logs:

\`\`\`bash
export FIDELIZA_ENVIRONMENT=homolog
export FIDELIZA_MAINTENANCE_CONFIRMED=YES
export FIDELIZA_APPROVE_MIGRATE=YES_HOMOLOG_ONLY
export FIDELIZA_APPROVED_SHA="$(git rev-parse HEAD)"
# Obrigatórias: DATABASE_URL, DJANGO_SECRET_KEY e demais variáveis Django;
# FIDELIZA_EXPECTED_DATABASE; FIDELIZA_EXPECTED_PG_HOST;
# FIDELIZA_RESTORE_VERIFY_DATABASE_URL;
# FIDELIZA_EXPECTED_RESTORE_PG_HOST; FIDELIZA_BACKUP_DIR.
bash scripts/homolog_backup_migrate.sh
\`\`\`

O script deve bloquear antes de escrever se: ambiente diferente de homolog,
SHA divergente, diretório inválido, banco/host divergente, scratch não vazio,
falta de confirmação de manutenção ou dump/restore falho.

Execução sob manutenção, **na ordem verificável**:

1. Gera \`pg_dump --format=custom\` com \`umask 077\` e arquivo separado.
2. Gera manifesto \`pg_restore --list\` e SHA-256, executa
   \`sha256sum --check\` no backup.
3. Faz restore em banco scratch vazio com \`pg_restore --single-transaction\`.
4. Compara contagens de tabelas legadas restauradas; **migra primeiro o
   scratch**, verifica migrations Django, triggers e FKs nessa cópia.
5. Só após a cópia migrada passar, executa
   \`python manage.py check\`, \`migrate --plan\` e
   \`python manage.py migrate --noinput\` no banco original declarado.
6. Executa \`migrate --check\`, \`check\`, auditoria das seis triggers,
   flags financeiras OFF, FKs e contagens das tabelas comerciais.
7. Guarda dump, manifesto, SHA-256, plano e logs em armazenamento privado.
   Não anexar o dump, logs com PII ou segredos a GitHub/ChatGPT.

**Observações:** \`pg_dump\` é consistente, mas não bloqueia escritores por
si só; a pausa de toda escrita é responsabilidade operacional.
O dump por DB não salva objetos globais do cluster (roles/tablespaces);
preservar também a configuração de infraestrutura/roles sob controle
separado. Scripts não devem adicionar dados comerciais no migrate.
Referências: PostgreSQL
https://www.postgresql.org/docs/current/app-pgdump.html e
https://www.postgresql.org/docs/current/app-pgrestore.html.

### Validação pós-migração independente

Com env da homologação real (não scratch), no diretório \`backend/\`:

\`\`\`bash
uv run --locked python manage.py showmigrations customers channels \
  sales loyalty points wallets
uv run --locked python manage.py migrate --check
uv run --locked python manage.py check
uv run --locked python scripts/homolog_post_migrate_check.py schema
\`\`\`

Depois, com \`DATABASE_URL\` da **role runtime da API** (não da role de
migração), executar:
\`\`\`bash
uv run --locked python scripts/homolog_post_migrate_check.py runtime
\`\`\`
Esse segundo modo rejeita role superuser, proprietária das tabelas do
ledger ou com direito a TRUNCATE. Se o atual usuário da API é owner, o
release fica **NO-GO** até separar roles e permissões; triggers não impedem
\`TRUNCATE\` nem um superuser desabilitar triggers.

## 3. Deploy manual no Coolify, sem ativação financeira

1. Conferir \`homolog\` e commit final exato aprovado; escolher
   **Git Compose RAW** no Coolify, não Managed.
2. Conferir que o serviço \`api\` executa apenas \`migrate --check\` no boot.
   Redis, worker, redes Docker e Traefik ficam internos conforme Compose.
3. Deploy **manual** e observação dos healthchecks; worker somente após
   API saudável. Confirmar pelos artefatos/labels/logs **qual SHA** está
   realmente publicado (não confundir commit no GitHub com deploy).
4. Confirmar \`/api/ready/\` HTTPS, DNS, certificado, redirects, páginas
   \`/app/visao-geral\` e \`/clube/<slug>\`. Não imprimir session cookies.
5. Validar novamente flags e roles PostgreSQL. Manter restrição financeira.
   Não reativar automações até a conclusão formal GO.

## 4. Preparar tenant QA e smoke HTTPS de verdade

**Não usar Bibelô, pedidos reais nem CPF/e-mail/telefone de clientes.**

Em homologação, um operador autorizado prepara UMA loja stand-alone
exclusivamente de testes, slug \`qa-...\` ou \`homolog-...\`, sem instalação
Nuvemshop, sem sales, sem wallets, sem loyalty grants/vouchers, com:
- participante QA ativo com consentimento e contato **E.164 previamente
  comprovado por OTP no fluxo autorizado** (não forjar prova);
- uma recompensa de catálogo marcada publicada somente no tenant QA
  (\`reward_id\` UUID). Publicar o catálogo não ativa o resgate;
- sessão privada de membro QA obtida pelo fluxo de acesso com link de
  e-mail autenticado. Guardar Playwright \`storageState\` em arquivo
  privado, fora do Git, e descartar após a janela;
- token Flow EXCLUSIVO desse tenant QA, armazenado no secret manager,
  jamais reaproveitado de produção.

Variáveis privadas exigidas:
\`FIDELIZA_ENVIRONMENT=homolog\`,
\`FIDELIZA_HOMOLOG_BASE_URL=https://fideliza-homolog.optarys.com.br\`,
\`FIDELIZA_SMOKE_CLUB_SLUG\`,
\`FIDELIZA_SMOKE_TENANT_ID\`,
\`FIDELIZA_SMOKE_PHONE_E164\`, \`FIDELIZA_SMOKE_FLOW_TOKEN\`,
\`FIDELIZA_EXPECTED_DATABASE\`, \`FIDELIZA_EXPECTED_PG_HOST\`,
\`DATABASE_URL\`, além das variáveis Django de homolog.

Primeiro auditar o tenant e a identidade, **somente SELECT**:
\`\`\`bash
cd backend
uv run --locked python scripts/homolog_smoke_db_audit.py pre
cd ..
\`\`\`

Smoke GET público, ainda sem criar pedidos:
\`\`\`bash
python3 scripts/homolog_http_smoke.py
\`\`\`

Após aprovação explícita de criar UMA venda sintética no tenant QA:
\`\`\`bash
export FIDELIZA_SMOKE_TENANT_CHECKED=YES_VERIFIED_QA_TENANT
export FIDELIZA_SMOKE_APPROVE_WRITES=YES_QA_ONLY
python3 scripts/homolog_http_smoke.py --write
\`\`\`

Espera-se \`ORDER_HTTP_SMOKE_OK\`: notificação pending → duplicata →
notificação paid, dois eventos persistidos, mesmo pedido, telefone já
comprovado vinculado ao perfil correto, \`payment_verified=false\`,
\`points_credited=false\` e \`cashback_credited=false\`.
O estado \`paid\` **é relato do canal**, não captura PSP validada.

Copiar somente a referência sintética \`PR24-...\` impressa, sem telefone:
\`\`\`bash
export FIDELIZA_SMOKE_ORDER_REF="PR24-REFERENCIA_GERADA_PELO_SCRIPT"
cd backend
uv run --locked python scripts/homolog_smoke_db_audit.py post
cd ..
\`\`\`
A auditoria cruza \`customers\`, \`SaleRecord\`, recibos,
\`FinancialEvidence\`, \`LoyaltyGrant\`, \`PointWallet\`, \`CashbackWallet\`
e vouchers: **zero crédito involuntário** e nenhum dado comercial real.

### Portal real no navegador (sem mocks)

O \`playwright.config.ts\` normal usa preview local e não demonstra o
Coolify publicado. O PR #24 inclui **config independente** que exige URL
HTTPS fixa, navegador e sessão QA real, com prints/trace/video desabilitados.

\`\`\`bash
cd frontend
# FIDELIZA_HOMOLOG_BASE_URL e FIDELIZA_SMOKE_CLUB_SLUG já definidos.
# FIDELIZA_HOMOLOG_STORAGE_STATE aponta para arquivo privado QA
# (gerado pelo login autorizado; NÃO anexar cookies a PR/logs).
npx playwright test --config=playwright.homolog.config.ts
\`\`\`

O navegador valida 320/390/768 px, rota pública, login privado com
storageState, VIP, carteira, botão de voucher indisponível, catálogo
com \`reward_id\`, POST real de emissão bloqueado com HTTP 409, histórico,
sem overflow horizontal nem erro JS. Não envia e-mail nem cria voucher.
**Não pode comprovar o sucesso de um resgate financeiro**, porque manter
as flags OFF é condição desta etapa. Anotar como gate posterior específico.

## 5. Recuperação / rollback de incidentes

- **Falha de checksum/restore/scratch migrate:** fonte original não migrou;
  não publicar a versão nova; revisar logs privados e infraestrutura.
- **Falha após migrate da origem:** suspender todo tráfego/escrita da aplicação,
  reter dump e logs, não reativar worker. Decidir com o responsável de dados
  se correção forward segura ou restauração isolada é a melhor opção.
- **Restaurar imediatamente sobre a base original pode apagar pedidos novos.**
  A restauração não é automática nem destrutiva: criar uma base NOVA privada
  vazia para recuperação, restaurar com \`pg_restore --single-transaction\`,
  conferir FK/integridade/contagens e, somente com aprovação, apontar
  \`DATABASE_URL\` de homologação para a base recuperada com escrita ainda
  bloqueada. Verificar compatibilidade do **código antigo** com o schema
  restaurado antes de retomar. Preservar a base falha para perícia.
- **Se já existirem escritas pós-backup:** NÃO restaurar diretamente sem
  reconciliar essas transações; optar por forward fix ou recuperação
  transacional controlada. Reverter branch Git não reverte schema nem dados.
- **Erro de integração do smoke:** NÃO concluir homologação; isolar
  o tenant QA e comparar dados por order_ref, sem editar dados legados.
- **Falha apenas visual:** manter gates financeiros OFF, bloquear GO de UI;
  corrigir frontend em PR separado e refazer Playwright remoto.

## 6. Evidências mínimas do relatório (somente metadados)

| Gate | Evidência exigida | Estado inicial |
|---|---|---|
| PRs #18→#23 | 6 merges/rebases/reviews e SHAs finais de homolog | NÃO EXECUTADO |
| Auto-deploy | Confirmação de desativação antes do primeiro merge | NÃO VERIFICADO |
| Freeze de escrita | Responsável, início/fim e checagem de writers | NÃO VERIFICADO |
| Backup PG | Caminho privado, tamanho, UTC, PG version, SHA-256 | NÃO EXECUTADO |
| Restore | Base scratch vazia, sucesso \`pg_restore -1\`, contagens | NÃO EXECUTADO |
| Scratch migrate | \`migrate --check\`, 6 triggers, FK=0 | NÃO EXECUTADO |
| Migração origem | Plano, log, \`showmigrations\`, SHA de código | NÃO EXECUTADO |
| Role runtime | Sem SUPERUSER/DDL ownership/TRUNCATE | NÃO VERIFICADO |
| Deploy Coolify RAW | SHA implantado + healthcheck + hostname HTTPS | NÃO EXECUTADO |
| HTTP Flow | 1 pedido QA, 2 eventos, 1 duplicado, ID verificado | NÃO EXECUTADO |
| Banco QA | Sem FinancialEvidence/grants/wallets/vouchers | NÃO EXECUTADO |
| Navegador | 320/390/768, sessão QA, recompensa bloqueada | NÃO EXECUTADO |
| Financeiro | Três flags OFF, nenhum adapter PSP autorizado | SEM VERIFICAÇÃO REAL |
| Rollback | Backup retido, owner e recuperação testada | NÃO EXECUTADO |

**GO:** todos os gates anteriores com evidências, ausência de impacto real,
documento assinado pelo responsável e release SHA aprovado.
**NO-GO:** qualquer campo pendente, divergência entre checkout e deploy,
origem inesperada, dúvida sobre backup, restrição financeira ou tenant.
Não inferir sucesso do CI sintético como sucesso da homologação operacional.
