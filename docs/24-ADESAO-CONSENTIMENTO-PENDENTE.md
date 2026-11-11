# Fase P0 — Convites e captura de aceite separado da identidade do comprador

Data: 11/11/2026. Branch exclusiva de trabalho: `homolog`.
A interface mantém o design v2, sem novas branches/PRs intermediários.

## Decisão de produto
Um programa não pode assumir que todo comprador é participante. Sem acesso
validado aos dados de clientes/pedidos da Nuvemshop, é incorreto criar
`ProgramParticipant` apenas porque alguém digitou nome e e-mail.

A entrega captura **o aceite real à versão de termos apresentada** e guarda
essa solicitação numa fila **`pending_verification`**. A adesão só virará
participação após uma etapa posterior de vínculo oficial com o cliente da
loja, que ainda não foi implementada.

## Fluxo do lojista
1. Área Clientes → Prepare seu programa. Um proprietário/admin preenche e
   aprova regulamento real da loja. Versão única `tenant + version`;
   nova versão desativa a anterior e invalida convites ainda não usados.
2. Gera convite individual temporário. Máximo 30 convites abertos por loja,
   60 gerados por janela de 24h. Token aleatório de 32 bytes, armazenado apenas
   como SHA-256; texto do token retorna uma vez à pessoa autorizada.
3. Compartilha a URL `/participar#convite=TOKEN` manualmente. O fragmento
   não é enviado no pedido HTTP; a pessoa realiza as chamadas em JSON.
4. Visualiza a fila de aceites aguardando verificação. Analista não pode
   consultar PII da fila nem criar convites.

## Fluxo do convidado
- Frontend público exibe a versão exata dos termos associados ao convite.
- Nome e e-mail são informados, com confirmação expressa dos termos.
- Checkbox de mensagens promocionais é **independente e desmarcado por padrão**.
- HTTP POST de confirmação exige cookie/token CSRF mesmo sem login.
- Convite expira após 24h, é consumido uma única vez e também perde validade
  se a versão dos termos foi substituída.
- Resposta informa `pending_verification`, sem promessa de crédito.

## Endpoints
- `GET/POST /api/v1/tenants/{tenant_id}/program-terms/`
- `POST /api/v1/tenants/{tenant_id}/enrollment-invitations/`
- `GET /api/v1/tenants/{tenant_id}/enrollment-submissions/`
- `POST /api/v1/public/enrollment/preview/`
- `POST /api/v1/public/enrollment/accept/`

Autenticação Django + CSRF para rotas privadas; as duas públicas usam
`AllowAny` com `csrf_protect` explícito, rate limit conservador,
token de entropia forte e `Cache-Control: private, no-store`.
Sem renderização HTML fornecida por comprador ou proprietário.

## Segurança e limitações
- Não cria `ProgramParticipant`, carteira, cashback, cupons,
  mensagens, pedidos ou descontos; não modifica Nuvemshop, tema Ipanema
  ou banco existente fora das migrações novas.
- Nome/e-mail informado e posse de link **não confirmam identidade**.
  A fila não é a lista de compradores, e nenhum aceite entra nas métricas
  de participantes ou recompra.
- Marketing opt-in não é autorização para envio automático do SaaS.
- Os termos devem ser redigidos e revisados pelo lojista e jurídico.
- Armazenamento de contato é dado pessoal: antes de piloto real estabelecer
  retenção, eliminação, exportação/retirada, transparência LGPD e responsáveis.
  **Não usar este formulário com público real até aprovar essas regras.**
- Não há sincronização de clientes/pedidos, webhooks ou reautorização OAuth.
  A identidade e concessões permanecem bloqueadas.
- A URL de convite aparece apenas após sua criação na UI e não deve
  ser compartilhada publicamente.

## QA
- Django: permissões/isolamento, termos versionados, token opaco,
  aceite único, payload estrito, CSRF anônimo, marketing separado,
  nenhuma inscrição real ou saldo criado.
- Playwright: fluxos públicos em 390, 768 e 1440 pixels.
- Migração nova `participants/0002_enrollment_terms_invites`.
- Publicação Coolify exige backup e revisão da proteção de dados;
  não foi feita nesta etapa.

## Continuação
Confirmar escopos oficiais de leitura de clientes/pedidos, registrar vínculo
verificado com o comprador e revisar identidade antes de transformar a fila
em participantes ativos. Separar aceite do programa, consentimento de
marketing e prova de pagamento. Somente então desenvolver crédito por pedido
pago, liberação, resgate e estorno.
