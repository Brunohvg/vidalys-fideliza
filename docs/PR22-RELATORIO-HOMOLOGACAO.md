# PR #22 — Relatório de consolidação e execução operacional em homologação

Data: 14/11/2026. Este relatório contém apenas evidência verificável; **não é declaração de deploy**.

## 1. Branches / merge seguro

| PR | Branch | Base atual | Head aferido | Estado |
| --- | --- | --- | --- | --- |
| #18 | refactor/omnichannel-customer-identity | homolog | 0853282be9cef0169b4d66cf7c4dd1b974c30d53 | draft |
| #19 | feature/pr19-channel-order-ingestion | #18 | 9d72304a6696439db679ca630577b21e49bc595e | draft |
| #20 | feature/pr20-loyalty-offline-engine | #19 | c7f7f9fa7cef269e614933c1e46ca1be33509647 | draft |
| #21 | feature/pr21-frontend-routes-visual-qa | #20 | fbfa046a12c22acc8acc11d288b8e4c4b2f45950 | draft |

A base homolog observada no início do PR #22 é c25d668ec1b668c3a254b816cc96b6236a0dadb2.
A branch #21 estava 38 commits à frente de homolog, sem divergência.
Conservar histórico e merges em ordem #18, #19, #20, #21, #22.
A criação de um PR empilhado não equivale a merge. Revalidar SHAs e CI antes de cada ação.

**Estado real**: sem merge em homolog. A conexão GitHub está autorizada, mas
não há sessão administrativa nem shell do Coolify/PostgreSQL disponíveis.
Não foi feito dump, restore, migrate ou teste autenticado HTTPS no ambiente real.

## 2. Risco crítico e mitigação de boot

Antes do PR #22 o compose.yaml executava `python manage.py migrate --noinput`
automaticamente na partida da API. Se Coolify fizesse auto-redeploy da branch,
o novo esquema poderia ser aplicado ANTES do backup.

Este PR troca o boot por `python manage.py migrate --check`. A API recusa
subir se existirem migrações pendentes; NÃO escreve no banco no boot.
O workflow de CI migra explicitamente SOMENTE em banco PostgreSQL 16 descartável.
Não implantar esta versão enquanto faltar backup validado — a API não iniciará
corretamente se o banco ainda não tiver sido migrado.

## 3. Pré-requisitos obrigatórios da operação

- Confirmar ambiente Coolify RAW, banco PostgreSQL externo, rede privada, branch,
  SHA publicado, janela de manutenção, segredos da homologação e eventual
  auto-deploy **desabilitado temporariamente**.
- Suspender processamento de pedidos/worker e garantir que o banco não receba
  novas escritas durante snapshot, migração e conferência. Não agir sobre produção.
- Ter permissões seguras e espaço para dump PostgreSQL FULL, com volume de backup
  privado fora do repositório, retenção e criptografia apropriadas.
- Separar um banco PostgreSQL **vazio, descartável e privado**, com nome terminando
  em `_restorecheck`, para verificar o restore sem sobrescrever o banco real.
- Dispor de `pg_dump`, `pg_restore`, `psql`, `git`, `flock`, `sha256sum`,
  `uv` e Python 3.12 no executor privado com acesso à rede do DB.
- Obter URL e segredos do gerenciador autorizado, não registrar em issues,
  pipelines ou documentos. Nunca inserir senha de loja em comandos do GitHub.

### Operação guardada

No checkout do SHA aprovado, conectado à rede privada do PostgreSQL:

```bash
# Exportar DATABASE_URL, FIDELIZA_RESTORE_VERIFY_DATABASE_URL,
# FIDELIZA_EXPECTED_DATABASE, FIDELIZA_BACKUP_DIR e DJANGO_SECRET_KEY
# exclusivamente pelo secret manager do operador.
export FIDELIZA_ENVIRONMENT=homolog
export FIDELIZA_MAINTENANCE_CONFIRMED=YES
export FIDELIZA_APPROVE_MIGRATE=YES_HOMOLOG_ONLY
export FIDELIZA_APPROVED_SHA="$(git rev-parse HEAD)"
bash scripts/homolog_backup_migrate.sh
```

O script bloqueia a operação se a base real divergir da declarada, se
a base de restauração não estiver vazia, se não existir confirmação de
manutenção ou se o SHA do código mudar. Faz:
1. Dump consistente em formato custom, no diretório privado (permissões 0700).
2. Manifesto e SHA256 do arquivo para integridade.
3. Restore **real** em banco privado descartável; comparação de contagens
   das tabelas comerciais com o dump.
4. `manage.py check` e plano de migração.
5. Migração explícita somente após restore comprovado.
6. `migrate --check`, `check`, FKs validadas e contagens comerciais estáveis.

**Não executar** o script na API existente sem binários PostgreSQL e acesso
correto à base descartável. A base de restore contém dados privados e não
deve ser exposta publicamente. Remover somente após aprovação e política
de retenção.

### Rollback

- Dump/restore falhou: não houve migrate; manter versão antiga e revisar.
- Migração falhou: interromper deploy, preservar logs e dump, manter banco
  isolado de novas escritas, diagnosticar transações e restaurar somente por
  procedimento separado e aprovado. O script **não** faz rollback automático
  destrutivo; nunca sobrescrever dados comerciais que já receberam novas
  transações.
- Deploy falhou após migração: não presumir que rollback só do aplicativo é
  compatível; verificar o esquema e usar estratégia validada de recuperação
  ou ajuste *forward*, sempre com backup retido.

## 4. Smoke integrado reproduzível — testes em CI

Teste sintético `backend/apps/channels/test_consolidation_smoke.py`, com
Django APIClient (views/serializers/serviços reais):
- Credencial Flow com escopo do tenant e evento pending;
- Reenvio idêntico: `duplicate=true`, mesmo sale_id/event_id;
- Transição paid com `requires_independent_capture`, não prova PSP;
- `customers.CustomerProfile` vinculado somente quando telefone já foi
  previamente comprovado via OTP sintético;
- Telefone sem prova cria perfil provisório, não sequestra participante;
- Cross-tenant com token de outra loja: HTTP 401;
- Participante autenticado apenas por challenge de e-mail privado,
  `GET /api/v1/public/clubs/{slug}/me/` e `GET /api/v1/public/clubs/{slug}/`;
- Verifica VIP/saldo/histórico vazios quando não há ledger e
  `redemption_enabled=false`;
- Evento refunded registra estado e recibo, sem criar cashback/pontos.

A suíte Playwright do PR #21 validou 320/390/768 px, login, navegação,
estado da carteira e bloqueio do botão de voucher; nenhum teste de tela
do CI significa acesso ao navegador real de homologação.
O CI do PR #22 usa Postgres descartável e contém também
`backend/apps/core/test_pr22_legacy_upgrade.py`, cujo propósito é
recuar o esquema ao legado, inserir venda de balcão e participante
sintéticos, avançar migrações e verificar preservação sem lançamentos.

## 5. Homologação real pendente — checklist de evidência

- [ ] Cópia externa do backup seguro: arquivo, SHA256, versão PG, data, volume;
  NÃO anexar dump ou credenciais à issue/PR.
- [ ] Restore de verdade em banco isolado com contagens conferidas.
- [ ] `showmigrations` de customers, channels, sales, loyalty, points, wallets
  sem pendências e `manage.py check` limpo.
- [ ] Resultado das FKs e contagens antes/depois; zero crédito involuntário.
- [ ] API `/api/ready/` com HTTPS e rota `/app/visao-geral` no SHA correto.
- [ ] Flow/PDV integrado com credencial **exclusiva de homolog**, usando
  telefone sintético não identificável; evento duplicado e mudança de status.
- [ ] Verificar que telefone desconhecido apenas cria perfil provisório;
  somente telefone previamente comprovado reaproveita cliente verificado.
- [ ] Login privado de consumidor e portal `/clube/{slug}`,
  histórico e estado sem pontos inexistentes; viewport 320 px.
- [ ] Confirmar que nenhuma publicação de cupom externo, cashback ou pontos
  foi ativada; G7 e G8 continuam BLOQUEADOS.
- [ ] Confirmar rollback operacional e autorização para liberar auto-deploy.
- [ ] Merges #18 → #19 → #20 → #21 → #22, SHAs e jobs completos anotados.

**NÃO considerar homologado nem marcar concluído um item sem log real.**
