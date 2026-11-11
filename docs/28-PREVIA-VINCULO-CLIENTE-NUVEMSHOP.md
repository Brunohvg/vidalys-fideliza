# Prévia de vínculo cliente Nuvemshop — READ ONLY, sem ativar cashback

Data: 11/11/2026. Branch: `homolog`. Integrado ao módulo
de consentimento/SMTP2GO sem mexer na `main` ou em lojas reais.

## Motivação

A confirmação de que alguém possui um endereço de e-mail não garante
que exista cadastro de cliente na Nuvemshop, nem que uma compra tenha sido
paga. Somente `read_products` estava autorizada no OAuth anterior.

A documentação oficial atual informa os scopes **`read_customers`** e
**`read_orders`** separados, e exige atualizar as permissões no
Portal de Parceiros e reinstalar a aplicação na loja para conceder
novos escopos. O URL OAuth não fornece scopes opcionais por instalação.

- Fonte: https://nuvemshop.dev/docs-api/authentication
- Fonte: https://nuvemshop.dev/docs-api/faq
- Customer GET e filtro por e-mail:
  https://nuvemshop.dev/docs-api/resources/unstable/customer
- Admin API 2025-03 e headers Authorization Bearer/User-Agent:
  https://nuvemshop.dev/en-US/api/getting-started

## O que a implementação permite (quando habilitada e autorizada)

1. `FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=0` por padrão.
   Com `0`, o callback OAuth continua permitindo apenas `read_products`;
   nenhuma busca de cliente é possível.
2. Com liberação explícita `1`, o callback permite **somente**
   `read_products,read_customers` além do escopo anterior; não
   permite escrita ou outro escopo não previsto.
3. Página Clientes mostra a situação da permissão da loja.
   Exige que o aceite esteja `email_verified` e não tenha sido retirado.
4. O administrador solicita explicitamente a prévia de uma **solicitação
   já confirmada**, sem poder informar arbitrariamente outro e-mail.
5. A API consulta `GET /2025-03/{store_id}/customers?email=...`
   no servidor usando o token cifrado da instalação da própria loja,
   `Authorization: Bearer`, `User-Agent`, HTTPS, sem redirects,
   retries proporcionais e resposta limitada.
6. Resultado: **correspondência única, nenhuma ou ambígua**,
   devolvendo no máximo o ID de cliente e indicadores de estado ao
   lojista autorizado; não replica telefone, endereço, documento,
   compras nem conteúdo integral da API.
7. A prévia é limitada a 1 solicitação por 60 s, isolada por loja,
   não altera banco e não cria `ProgramParticipant`, pontos ou cashback.

## API

`POST /api/v1/tenants/{tenant_uuid}/enrollment-submissions/{submission_uuid}/customer-match/preview/`

Payload: `{}` (obrigatoriamente vazio).

Resposta de sucesso:

```json
{
  "mode": "read_only_customer_match_preview",
  "status": "one_exact_match",
  "customer_id": "123",
  "email_verified": true,
  "scope_required": "read_customers",
  "writes_performed": 0,
  "participant_created": false,
  "cashback_enabled": false
}
```

A resposta completa inclui o identificador de tenant/solicitação, nota e
é enviada com `Cache-Control: private, no-store`.
Quando houver múltiplas contas ou lista cheia, não escolher uma
automaticamente. Não criar cadastro de clientes que não existam.

## Segurança e limites

- Isolamento `tenant`, OWNER/ADMIN, sessão autenticada, CSRF do DRF,
  impossibilidade de buscar e-mail arbitrário.
- Verificação `email_verified_at` e `status=email_verified`,
  bloqueando solicitação retirada ou não confirmada.
- Conferência do `store_id` da instalação OAuth com a loja vinculada.
- Rejeição de escopos inesperados, principalmente `write_*`.
- Credenciais nunca expostas ao navegador ou copiadas para logs.
- Prévia não é adesão final nem prova de compra/pagamento.
- Não alterar permissões do app no Portal de Parceiros nesta etapa.
  A `read_customers` requer decisão explícita e reautorização da loja.
- `read_orders` será objeto de etapa posterior e **não** é solicitado
  automaticamente por esse recurso.
- Em API de clientes retornando erro, sem conexão ou token inválido,
  dar mensagem neutra, sem dados sensíveis.

## Testes adicionados

`backend/apps/participants/test_customer_link_preview.py` verifica
escopos de leitura/negação de escrita, OAuth flag off/on, constrangimentos
de tenant e perfil, exigência de confirmação, resultado ambíguo,
ausência de escrita, e parâmetros básicos do GET Nuvemshop.
CI continua testando backend, frontend, Docker, banco externo,
Compose Coolify e Playwright.

## Próximo avanço de produto

- Realizar reautorização controlada `read_customers` somente depois
  de escopo aprovado no Portal de Parceiros e consentimento da loja.
- Implementar revisão/aprovação do vínculo, com idempotência,
  trilha de auditoria e direito de retirada.
- Quando houver participante verificado, consultar pedidos pagos
  com scope `read_orders` (separado), conciliar cancelamentos/reembolsos
  e depois habilitar crédito pendente, resgate e estorno.
- Domínio personalizado `fideliza.bibelo.com.br` permanece planejado,
  não provisionado.
- Nenhum deploy Coolify, cadastro real, permissão externa ou envio
  de e-mail real foi executado nesta entrega.

**Não habilitar `FIDELIZA_PUBLIC_SIGNUP_ENABLED` nem
`FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED` em produção sem gates
jurídicos, autorização, backup e validação operacional.**

## Continuidade implementada — 11/11/2026: aprovação explícita do vínculo

O fluxo `read_only_customer_match_preview` foi mantido. Acrescentamos
`POST /api/v1/tenants/{tenant_uuid}/enrollment-submissions/{submission_uuid}/customer-match/approve/`
com `{"customer_id":"<id_confimado_na_previa>","confirm":true}`.

A API reconsulta via **GET** o mesmo cadastro Nuvemshop e exige correspondência
única com o e-mail já confirmado, tenant/loja iguais, usuário OWNER/ADMIN e
consentimento não retirado. Uma transação serializada por loja registra
`EnrollmentCustomerLink` e um `ProgramParticipant` com o número de cliente
verificado, termos, data de aceite e quem aprovou. Nova tentativa com o
mesmo vínculo devolve o mesmo participante; conta já vinculada por
outra solicitação não é adotada automaticamente.

O cliente então aparece na lista de Participantes; nenhum saldo é criado,
nenhum pedido é alterado, nenhuma API de escrita da Nuvemshop é chamada.
Se ele retirar a adesão pelo link confirmado de e-mail, o participante
é marcado `withdrawn`, marketing opt-in fica falso e os dados de
auditoria são preservados.

**Gate de segurança:** `FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=0` por
padrão. A opção também depende da prévia `read_customers` estar
ativada, do token da loja conter autorização de clientes e de
aceite realmente confirmado. Essa flag permite adesão auditada, não
cashback, resgate, campanhas ativas nem comunicação promocional.

Nova migração: `participants/0005_customer_link_approval`.
Testes: `test_customer_link_approval.py` e QA Playwright de aprovação.

**Ajuste de OAuth:** não exigir conjunto *exato* de escopos. O token
pode incluir `read_orders` e outras permissões concedidas; isso não
liga a leitura de pedidos nem operações de escrita automaticamente.
Quando um scope de escrita implica leitura no contrato Nuvemshop, o
Fideliza aceita o token mas continua restrito aos métodos GET do app.
A situação "permissão recebida" é distinta de "funcionalidade ligada".
