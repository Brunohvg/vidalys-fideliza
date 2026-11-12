# Auditoria de configuração e aprovação automática Nuvemshop

Referência: 11/11/2026 (America/Sao_Paulo) — apenas `homolog`.
**Não significa que as flags estejam ligadas no Coolify publicado.**
A ideia da integração com Vidalys Flow permanece em `docs/36`;
**não foi implementada neste ciclo**.

## Auditoria do que parecia duplicado

| Ponto | Diagnóstico | Tratamento |
|---|---|---|
| `read_customers` exigia `read_products` | **Dependência incorreta**: scopes distintos na API oficial | Corrigido `has_customer_access` e `allowed_scopes`, testes próprios |
| Revalidação manual e automática de vínculo | Poderia duplicar regras e facilitar divergências LGPD | Centralizada em `customer_link_service.py`, com lock e proteção de tenant |
| `NuvemshopStatusView` buscava a Membership várias vezes | Consultas repetidas sem benefício funcional | Calcula conexão/escopos/capacidades uma vez |
| Frontend validava cores claras, backend rejeitava | **Inconsistência concreta de configuração**, não mero CSS | Frontend usa `brand-contrast.ts` no preview/página pública; backend aceita hex válido e os testes checam contraste |
| SMTP tinha um `return False` repetido | Código redundante sem efeito | Removido |
| `DB_HOST` e `DATABASE_URL` | Dois caminhos legado/novo; Django dá precedência ao `DATABASE_URL` | Auditoria em runtime alerta se ambos forem informados |
| `compose.yaml` único | A stack do Coolify e o CI usam a mesma definição e banco externo | Não restaurar Compose antigo; conferir Deployable Compose no servidor |
| `.env.example` e `.env.coolify.external-db.example` | Ambientes distintos; não são duas fontes de verdade da mesma implantação | Local x referência de deploy; fonte real da hospedagem é a Application do Coolify |
| Flags em API/worker/Redis/frontend | Coolify pode herdar `env_file` por serviço; flags e segredos poderiam atravessar limites | Bloqueio explícito de flags API nos outros serviços, inspeção de precedência no CI |
| Preferências do lojista e ambiente | Nome/cores/e-mail de contato são **dados por tenant**; permissões OAuth, SMTP e scripts são **config de infraestrutura** | Manter separados: não entregar credenciais ao lojista, não duplicar setting por cliente |

**A configuração OAuth não pode ser alterada simplesmente pela seleção
de scopes no browser.** Segundo a documentação oficial, os scopes
ficam no Portal de Parceiros e exigem reinstalação do app após mudança.

Documentação consultada:
- https://nuvemshop.dev/docs-api/authentication
- https://nuvemshop.dev/docs-api/resources/2025-03/webhook

## Aprovação automática — regra implementada

O sistema **não precisa de aprovação manual para cada adesão** quando
todas as evidências abaixo existem:

1. O cliente aceita voluntariamente os termos e o aviso de privacidade
   da loja.
2. O token de e-mail emitido e confirmado é válido, de uso único e não
   foi utilizado para retirada.
3. A loja está ativa e vinculada à instalação Nuvemshop correta.
4. A instalação tem escopo `read_customers` ou `write_customers`
   concedido; a aplicação **somente faz GET**, nunca grava na loja.
5. Consulta oficial limitada devolve **uma única** conta Nuvemshop com
   o mesmo e-mail exato, já confirmado pelo cliente.
6. Não existe participante ou vínculo anterior, divergência de cliente
   nem protocolo `customer/redact` que impeça reativação.
7. Dentro de transação, o backend bloqueia o tenant, reconfirma os
   requisitos e cria apenas **ProgramParticipant + EnrollmentCustomerLink**.
   O vínculo automático usa `confirmed_by=null` e `source=
   nuvemshop_customer_auto_verified_email` para manter rastreabilidade.

Se qualquer condição falhar, a adesão fica em `email_verified`.
O lojista recebe somente os casos não resolvidos para revisão,
sem presumir que ausência de resposta seja aprovação. Um segundo
clique no link consumido não cria outra adesão.
Nenhum `CashbackEvent`, carteira com créditos, lançamento, pedido
ou resgate é criado.

**Importante:** confirmar a posse do e-mail e encontrar um cadastro
correspondente é a evidência adotada para o piloto. Isso não é uma
prova universal de identidade; cadastros compartilhados/ambíguos ou
situações especiais exigem atendimento humano.

## Como habilitar de verdade na homologação

Não ativar variáveis em produção sem validar o destino e o backup.
Antes da ativação:

1. No Portal de Parceiros Nuvemshop: configurar a Redirect URL oficial
   `https://fideliza-homolog.optarys.com.br/api/v1/oauth/nuvemshop/callback/`.
   Conceder no mínimo `read_customers` para vínculo de contas e
   `read_products` se a prévia de catálogo também for utilizada.
   A leitura de pedidos read_orders já está implementada em prévia e inbox,
   sempre sob flags desligadas; não autorizar para produção sem piloto.
2. Reinstalar o aplicativo **na loja de TESTES** após qualquer mudança
   de escopos, permitindo obter token com as permissões atualizadas.
3. Verificar na Application de homologação do Coolify as variáveis
   `NUVEMSHOP_CLIENT_ID`, `NUVEMSHOP_CLIENT_SECRET`,
   `NUVEMSHOP_TOKEN_KEYS`, `NUVEMSHOP_OAUTH_CALLBACK_URL`
   e `NUVEMSHOP_API_USER_AGENT`, restritas ao serviço API.
   Nunca mostrar o conteúdo ou copiá-lo para documentações/logs.
4. Confirmar no worker SMTP2GO, remetente autorizado, HTTPS e
   caixa de destino de testes. Nenhuma senha SMTP na API.
5. Configurar as flags da Application para o piloto, **nessa ordem**
   e somente depois das verificações:
   - `FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=1` (API);
   - `FIDELIZA_PUBLIC_SIGNUP_ENABLED=1` (API, após regulamento/privacidade);
   - `FIDELIZA_EMAIL_DELIVERY_ENABLED=1` (API e worker);
   - `FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=1` (API: revisão excepcional);
   - `FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED=1` (API: aprovação automática).
6. **Não configurar** `FIDELIZA_LEDGER_WRITES_ENABLED=1`.
   No código, a concessão de cashback real continua bloqueada.

Antes de aplicar ao Coolify, usar somente scripts de diagnóstico
sem dados pessoais:

```sh
python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
python scripts/inspect_loyalty_journey.py --slug SLUG_DA_LOJA_DE_TESTE
```

O registro da loja de teste é necessário; o texto acima não presume
que ela já existe. Verificar em runtime os IDs/escopos, TLS, Redis,
sessão CSRF, fila e credenciais **por indicadores e sem revelá-las**.

## Critérios de teste a executar

- Teste unitário: um customer exato após e-mail verificado →
  participante criado sem ação humana, fonte registrada, zero crédito.
- Escopo `read_customers` isolado → permitido somente se flag ativada;
  `read_products` isolado → NÃO vincula cliente.
- Sem correspondência, duplicidade, rede indisponível →
  nenhuma aprovação, estado fica `email_verified`.
- Loja suspensa → confirmação bloqueada;
  `customer/redact` → nunca reativar o Customer.
- Reenvio do token → HTTP 410; sem duplicidade de participante.
- Acesso de outra loja → negado; retirada desativa participação.
- Testes frontend: botão e cores contrastantes, layout mobile e
  apresentação da revisão humana apenas quando for necessária.
- Teste humano: OAuth reautorizado na Nuvemshop com loja fictícia,
  e-mail em caixa controlada, aprovação automática sem toques extras,
  e simulação de indisponibilidade com rota de revisão manual.

## Próximos passos após esta etapa

1. Validar CI do SHA exato e confirmar versão publicada no Coolify.
2. Revisar credenciais/escopos e habilitar as flags do piloto
   **somente na Application correta**.
3. Executar a jornada com cliente sintético; conferir evidência no
   banco de homologação sem revelar identificadores.
4. Evoluir para comprovação de pedidos pagos na Nuvemshop:
   webhooks `order/paid` e `order/updated`, leitura autoritativa,
   idempotência, reversões e reconciliação de pagamento. `order/paid`
   também pode ocorrer por marcação administrativa; não confundir
   com prova irrevogável de liquidação.
5. Somente depois desenvolver concessões financeiras, prazos,
   estorno, expiração e resgate.
6. Futuramente implementar o conector Vidalys Flow já documentado,
   sem dividir banco de dados ou identidade sem validação.

**Escopo desta mudança:** código e documentação na `homolog`;
sem mexer na `main`, no Flow, em uma loja real ou no Coolify.


## Auditoria da interface: conexão em um só lugar

A autorização e reautorização OAuth são administradas apenas em **Configurações**.
A área **Conciliação** mantém a amostra oficial somente leitura e um atalho
para Configurações, sem repetir botão de autorização, IDs técnicos ou scopes.
O retorno do OAuth abre Configurações, limpa os parâmetros da URL e só
informa conexão confirmada após consultar o status real do backend.
Testes Playwright verificam esta separação, o perfil de analista, prévia de
catálogo e a navegação de retorno em 390, 768 e 1440px.
Nenhuma flag de homologação foi ligada na infraestrutura por esta alteração.


## G2 — Status de conexão e prova de leitura (12/11/2026)

A tela em Configurações **não confunde a existência de um registro OAuth com token ainda válido**. O status existente agora inclui `connection_check` com a ação concreta: ativar tenant, configurar o aplicativo, autorizar a instalação, conceder `read_products` com reinstalação ou confirmar acesso por GET de catálogo. Nenhuma nova variável ou endpoint foi criado.

- `connected` significa autorização registrada para o par app/loja; não é verificação viva.
- `live_access_checked=false` no status (a consulta de status não chama a Nuvemshop).
- Somente um GET autenticado na loja de teste comprova que o token atual funciona. A funcionalidade existente de **Conciliação → Consultar 3 produtos** faz essa leitura com token do próprio aplicativo, sem escrita.
- Permissões são configuradas no Portal de Parceiros e alteração de escopos exige reinstalação; nenhuma flag pode ampliar permissões OAuth por conta própria.
- Dados sensíveis (client_secret, access_token e Fernet) não são expostos no JSON ou na tela; `FIDELIZA_LEDGER_WRITES_ENABLED=False` continua fixo.
- Ambiente real: ainda falta usuário administrativo de homologação confirmado e credenciais oficiais do app autorizadas; o teste sintético valida somente o código. Não habilitar loja real nem cashback por este passo.

Documentação oficial: https://nuvemshop.dev/docs-api/authentication .


## G2 — prova de leitura sob demanda em Configurações (12/11/2026)

O proprietário/admin pode usar **Verificar acesso à Nuvemshop** em Configurações, sem abrir outra página. A ação reutiliza a rota já implementada `GET /api/v1/tenants/:id/nuvemshop/catalog/preview/?page=1`, que consulta até três produtos com o token cifrado do próprio aplicativo. Não cria endpoint, variável, migração, credencial ou rotina de sincronização.

- A verificação só ocorre por clique explícito de proprietário/admin e loja ativa com instalação registrada e escopo de catálogo disponível.
- GET de uma página vazia é sucesso de comunicação/autorização; não representa ausência de produtos no catálogo todo.
- Estado de êxito é **temporário nesta sessão**, não persistido nem reusado após troca de loja; não afirma que o token nunca será revogado.
- Falha de API mantém estado **não verificado**, com mensagem genérica e sem vazamento de tokens, IDs ou resposta bruta do provedor.
- Endpoint existente protege tenant, autenticação, throttling e recusa gravações na loja. O flag de crédito real continua false.
- Testes Playwright cobrem sucesso, falha e ausência do botão para analista; callback OAuth apenas afirma autorização registrada até um GET vivo.

**Próxima prova externa:** usando a conta QA recém-criada em homologação, testar login/sessão/logout, auditar SMTP do worker e só então autorizar a instalação do aplicativo oficial em loja piloto autorizada. Nenhuma loja externa foi conectada por esta alteração.
