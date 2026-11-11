# SMTP2GO compartilhado com o Mérito — confirmação de e-mail no Vidalys Fideliza

Data da decisão: 11/11/2026. Repositório: `Brunohvg/vidalys-fideliza`, somente branch `homolog`.

## Decisão e fonte

Reutilizar a infraestrutura SMTP2GO já usada no Mérito (repositório
`Brunohvg/QueroLink`, branch `querolink-v2`), sem contratar outro
serviço por enquanto. O proprietário informou que autorizou o domínio de
envio `vidalys.com.br`.

**Isso confirma uma autorização relatada, não constitui teste autenticado**
dos valores no Coolify, entrega real, SPF/DKIM/DMARC, cota do provedor,
nem disponibilidade de SMTP em cada container.

Variáveis compatíveis com Mérito:

| Nome | Configuração esperada |
| --- | --- |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | `mail.smtp2go.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | Configuração autorizada existente (`gmail-vidalys`) |
| `EMAIL_HOST_PASSWORD` | Segredo somente na variável protegida do Coolify |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_USE_SSL` | `False` |
| `DEFAULT_FROM_EMAIL` | `Vidalys <contato@vidalys.com.br>` |
| `SERVER_EMAIL` | `Vidalys <contato@vidalys.com.br>` |

A amostra sem credenciais está em `.env.coolify.external-db.example`.
O arquivo real de configuração e senhas nunca deve ser commitado.

## Arquitetura de segurança

- **API:** `FIDELIZA_EMAIL_DELIVERY_ENABLED` e
  `FIDELIZA_PUBLIC_BASE_URL`, mas sem senha SMTP.
- **Worker Celery:** recebe o mesmo gate e base URL, mais as variáveis
  `EMAIL_*` e `SERVER_EMAIL`.
- **Cache e broker:** Redis privado da stack Fideliza.
- O desafio possui UUID aleatório e token derivado via HMAC-SHA-256
  com a chave forte do Django e a finalidade da ação. Só o digest
  SHA-256 do token é persistido.
- A tarefa Celery recebe **somente o UUID do desafio** via broker;
  reconstrói o token com o mesmo segredo do Django antes de enviar.
  Não há link/token em texto puro na mensagem Redis ou no banco.
- API/SMTP nunca devem registrar link/token, destinatário, senha ou headers.
- O link tem duração de 30 minutos, é individual, de uso único e
  não é aceito para a ação oposta.
- Comunicação é **transacional**, não depende do aceite separado de marketing.
- A fila de participação continua separada de clientes verificados da
  Nuvemshop e de qualquer concessão de pontos ou cashback.
- A verificação de e-mail **não confirma o ID do cliente da Nuvemshop**.
- A retirada cancela a solicitação, desativa o opt-in promocional e
  invalida os demais tokens. Não remove automaticamente o registro
  de evidência e não afeta compras anteriores.
- Filas de solicitação excluem registros retirados da visão operacional.
- API de solicitação de retirada retorna mensagem genérica para evitar
  descoberta de e-mails cadastrados.
- O envio é fail-closed: `FIDELIZA_EMAIL_DELIVERY_ENABLED=0` por padrão;
  worker requer SMTP backend real e TLS/SSL; console backend nunca envia
  tokens para logs reais.
- O cadastro público continua com `FIDELIZA_PUBLIC_SIGNUP_ENABLED=0`
  por padrão, independentemente da liberação do SMTP.

## Fluxo

1. Lojista aprova regulamento e aviso de privacidade, ainda sem publicação.
2. Em ambiente validado com flags deliberadamente habilitadas, comprador
   solicita adesão e recebe mensagem para confirmar e-mail.
3. API persiste desafio de hash e enfileira após a confirmação da transação.
4. Worker Celery envia e-mail com URL canônica:
   `https://fideliza-homolog.optarys.com.br/confirmar#acao=verify&token=...`.
5. Cliente abre e confirma por POST protegido por CSRF. Estado:
   `email_verified`. Isso não cria participante da loja nem cashback.
6. Cliente solicita retirada em `/retirar/{slug}`.
   Se houver solicitação correspondente, recebe link para
   `/confirmar#acao=withdraw&token=...`.
7. Confirmação de retirada resulta em `withdrawn`,
   `marketing_opt_in=False` e tokens consumidos.
8. O lojista vê a situação de e-mail na fila **Clientes**,
   sem acesso ao conteúdo do token.

## Contrato de variáveis adicionais

```env
FIDELIZA_EMAIL_DELIVERY_ENABLED=0
FIDELIZA_PUBLIC_SIGNUP_ENABLED=0
FIDELIZA_PUBLIC_BASE_URL=https://fideliza-homolog.optarys.com.br
```

**Não alterar as flags para 1 apenas com a autorização do domínio de envio.**
Ainda faltam fluxos reais de titularidade, retirada/eliminação adequada,
texto jurídico aprovado, acesso consentido a clientes Nuvemshop, teste
de SMTP no worker e proteção de tráfego externo.

## Auditorias sem credenciais

Dentro do serviço `api`:

```sh
python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
```

Dentro do `worker`:

```sh
python scripts/audit_smtp_env.py --host fideliza-homolog.optarys.com.br
```

Para exigir que o envio tenha sido explicitamente habilitado no worker:

```sh
python scripts/audit_smtp_env.py --host fideliza-homolog.optarys.com.br --require-enabled
```

Os scripts apenas inspecionam nomes/configurações; **não enviam e-mail e não
testam a autenticação no SMTP2GO**.

## Testes automatizados

`backend/apps/participants/test_email_proof.py` cobre:
token de uso único e expiração, token trocado entre ações, retirada
desativando marketing e tokens, resposta indistinguível para e-mails
existentes/inexistentes, CSRF, mail backend fictício, cabeçalhos/remetente e
ausência de `ProgramParticipant`.

`frontend/e2e/enrollment.visual.spec.ts` cobre o fluxo público em
390px/768px/1440px, sem chamadas SMTP reais.

## Gaps e decisões futuras

- Implementar confirmação real de identidade do cliente na Nuvemshop
  e resgates idempotentes.
- Criar retenção/eliminação/exportação dos dados pessoais conforme política.
- Confirmar SPF, DKIM, DMARC, remetente e quota no painel SMTP2GO;
  evitar que e-mails transacionais do Fideliza concorram descontroladamente
  com o Mérito por quota.
- Diagnosticar retry de envio sem expor dados sensíveis ou links.
- Confirmar que o serviço Worker do Coolify recebeu todas as envs de SMTP.
- Fazer backup, migrar `participants/0004_enrollment_email_proof`,
  e validar com e-mail de teste autorizadamente antes de abrir ao público.
- Não houve publicação no Coolify nem envio de mensagens reais nesta etapa.
