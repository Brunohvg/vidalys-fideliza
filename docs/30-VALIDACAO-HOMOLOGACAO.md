# Validação operacional da homologação

O estado `Running` confirma processos, não os fluxos do produto. Cada deploy
deve ficar associado a um commit fixo, aos testes desse código e às verificações
do ambiente efetivamente publicado. Não usar `HEAD` durante desenvolvimento
concorrente para afirmar que uma versão foi homologada.

## Antes do deploy

Contrato atual: Compose Location compose.yaml, com PostgreSQL externo.
A mudança no repositório não promove o arquivo automaticamente no Coolify.
Ver docs/44 e 45.

1. Revisar diferenças, migrações e contrato de variáveis. Fazer backup privado
   do PostgreSQL antes de aplicar novas migrações; não imprimir credenciais.
2. Executar backend, frontend, build e `makemigrations --check --dry-run`.
3. Executar `python .github/scripts/check_coolify_env_isolation.py`.
   Ele reproduz a injeção global de `.env` pelo Coolify com valores sintéticos.
4. Conferir CI do SHA exato, incluindo testes visuais. Job pendente não é aprovado.

## Depois do deploy

No terminal da API, sem copiar valores de variáveis:

```sh
python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
FIDELIZA_SMOKE_HOMOLOG=1 python scripts/smoke_homolog.py
```

O smoke exige o host e nome exatos do banco de homologação, as funcionalidades
externas desligadas e consentimento explícito pela variável temporária do comando.
Cria registros sintéticos dentro de uma transação revertida, usa usuários sem
senha utilizável e verifica autenticação interna, CSRF, isolamento entre lojas,
papéis, rascunhos, configurações versionadas/auditadas, desafios de e-mail,
retirada, bloqueio de cashback e ausência dos registros ao terminar. Não envia
e-mail nem faz requisições à Nuvemshop. Usa Django TestClient; não comprova o
formulário de login no navegador nem a passagem pelo proxy HTTPS.

Separadamente, pelo endereço HTTPS público, verificar saúde/readiness, sessão
anônima sem dados privados, cookie CSRF Secure/SameSite e rejeição de POST sem
CSRF. Confirmar commit, migrações, Redis e registro da tarefa no worker.
Conferir presença de credenciais por serviço somente como booleanos:
API sem SMTP; worker sem OAuth; frontend/Redis sem credenciais da aplicação.
No worker, `python scripts/audit_smtp_env.py` aponta configuração pendente sem
revelar valores. Não ativar envio para contornar senha ausente.

## Revisão visual

Validar navegação e estados em 390, 768 e 1440 px, usando os testes Playwright
e revisão real do painel. Se o navegador de testes não executar ou o CI ficar
na fila, registrar a limitação; build e testes de API não substituem essa revisão.
Não promover para produção a partir de um deploy de homologação isoladamente.
