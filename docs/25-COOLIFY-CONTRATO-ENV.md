# Auditoria da stack de homologação com PostgreSQL independente

Data: 11/11/2026. Ambiente identificado por histórico:
`fideliza-homolog.optarys.com.br`. Banco separado na rede privada
`fideliza-homolog`. Não alterar outros recursos do Coolify.

## Contrato de variáveis
**Compose recomendado:** `compose.coolify.external-db.yaml`
**NÃO usar:** `compose.coolify.yaml` (legado com DB embutido; mantido
exclusivamente para smoke de regressão no CI).

| Nome no Coolify | Status | Destino |
|---|---|---|
| `DATABASE_URL` | Obrigatória | API e worker; URI PostgreSQL na rede privada |
| `DJANGO_SECRET_KEY` | Obrigatória | API e worker, mesmo valor, forte |
| `DJANGO_ALLOWED_HOSTS` | Obrigatória | API e worker, incluir host público |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Obrigatória | API e worker, HTTPS do host público |
| `DJANGO_DEBUG` | Forçada a 0 | Do Compose, não sobrescrever |
| `DJANGO_SECURE_SSL_REDIRECT` | Forçada a 1 | Do Compose, proxy HTTPS |
| `REDIS_URL` | Do Compose | API e worker, Redis privado |
| `CELERY_BROKER_URL` | Do Compose | API e worker, Redis privado |
| `NUVEMSHOP_CLIENT_ID` | Opcional | Somente API |
| `NUVEMSHOP_CLIENT_SECRET` | Opcional | Somente API |
| `NUVEMSHOP_TOKEN_KEYS` | Opcional | Somente API |
| `NUVEMSHOP_OAUTH_CALLBACK_URL` | Opcional | Somente API |
| `NUVEMSHOP_API_USER_AGENT` | Opcional | Somente API |

OAuth exige as cinco variáveis completas e callback
`https://fideliza-homolog.optarys.com.br/api/v1/oauth/nuvemshop/callback/`.
Não configurar valores de exemplo como reais, não expor segredos,
não ativar permissões `read_customers`/`read_orders` sem consentimento.

## Auditoria sem imprimir valores de segredo
Dentro do container `api` em homologação:

```sh
python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
```

O script informa nomes e estados (OK/FALHA/ALERTA/DESLIGADO)
e código de saída 1 se alguma variável obrigatória falhar.
O CI executa a mesma auditoria com host `staging.invalid` e
PostgreSQL efêmero isolado.

## Risco identificado
Há dois padrões históricos no repositório. O antigo usa
`FIDELIZA_DJANGO_SECRET_KEY` e `FIDELIZA_DB_PASSWORD` para DB
embutido; o atual exige `DJANGO_SECRET_KEY` e `DATABASE_URL`.
Misturar os dois resulta em stack inválida ou aplicação em outro DB.

Esta alteração corrige a **documentação e a validação de código**.
Os valores no painel autenticado do Coolify não foram inspecionados.
Não afirmar que o runtime foi corrigido ou atualizado até uma
auditoria autenticada no recurso certo, sem mostrar credenciais.

## Checklist de atualização no Coolify
1. Abrir o recurso de homologação existente e confirmar branch `homolog`,
   compose `compose.coolify.external-db.yaml` e banco separado.
2. Conferir contexto de variáveis do deploy efetivo (Production), sem
   copiar segredos para chat/repositório.
3. Executar auditoria no container `api`; corrigir somente nomes e
   configurações erradas; nunca recriar BD ou volumes.
4. Backup validado do PostgreSQL antes de novas migrações;
   depois validar login/CSRF, /api/ready/, Celery e isolamento.
5. Comparar commit implantado ao HEAD da `homolog`; CI aprovado
   não prova que deploy foi realizado.

`main` não recebe alterações sem promoção homologada. Não adicionar
novas branches de desenvolvimento ou PRs permanentes.

## Bloqueio explícito da adesão pública

`FIDELIZA_PUBLIC_SIGNUP_ENABLED=0` é a configuração padrão (segura).
O Compose com banco externo passa o valor somente para a API.
Habilitar `1` abre os endpoints de pré-adesão por loja e de convite,
permitindo coletar nome e e-mail **sem conceder benefícios**.

**Não ativar** antes de revisar os termos e a privacidade, confirmar
responsáveis, retenção e retirada, teste anti-bot, verificação de identidade
e processo operacional de atendimento aos titulares. A auditoria sem
segredos retorna **ALERTA** se essa variável estiver ativada.

A mudança de código não modifica automaticamente as variáveis salvas
na interface do Coolify.
