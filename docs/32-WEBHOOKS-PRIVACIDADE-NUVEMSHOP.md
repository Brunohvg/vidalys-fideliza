# Webhooks obrigatórios de privacidade Nuvemshop — etapa segura de recepção

Data: 11/11/2026. Implementado em `homolog`; **não ativado na conta real**.

Fonte oficial, Admin API 2025-03 (atualizada em 29/10/2026):
https://nuvemshop.dev/docs-api/resources/2025-03/webhook
https://nuvemshop.dev/docs-api/authentication

## Os três webhooks obrigatórios

No Portal de Parceiros do **aplicativo Vidalys Fideliza** configurar, somente
após homologação operacional e HTTPS confirmado:

| Campo do Portal | Tópico oficial | URL da homologação proposta |
|---|---|---|
| URL Webhook Customer Redact | `customer/redact` | `https://fideliza-homolog.optarys.com.br/api/v1/webhooks/privacy/customer-redact/` |
| URL Customers Data Request Webhook | `customers/data_request` | `https://fideliza-homolog.optarys.com.br/api/v1/webhooks/privacy/customers-data-request/` |
| URL Webhook Store Redact | `app/store_redact` | `https://fideliza-homolog.optarys.com.br/api/v1/webhooks/privacy/store-redact/` |

**As URLs foram implementadas no repositório, mas não foi comprovada
instalação desse commit no Coolify, nem cadastro delas no Portal de Parceiros.**
Não usar as URLs propostas como prova de que o webhook já funciona externamente.

## Contrato de segurança

- Requisição externa **POST** HTTPS com `Content-Type: application/json`.
- Corpo máximo 64 KiB; rejeitar JSON e identificadores malformados.
- Validar **HMAC-SHA256 hexadecimal** do corpo original (sem reserializar),
  com `NUVEMSHOP_CLIENT_SECRET` e o header
  `X-Linkedstore-Hmac-Sha256`. Comparação de tempo constante.
  O token OAuth da loja **não é** a chave da assinatura.
- Extrair somente `store_id`, ID de Customer e ID da solicitação.
  **Não persistir** body, email, telefone, CPF, endereço ou pedidos do
  payload em `PrivacyWebhookRequest`.
- ID da loja precisa corresponder ao `external_store_id` local e,
  havendo instalação, ao `client_id` do aplicativo correto.
- Deduplicar por evento lógico: tipo + loja + Customer + ID da requisição.
  Atributos de reenvio não geram uma nova execução.
- Isolamento por tenant, transação de banco e resposta `202` apenas
  após registro persistido. Falha na transação devolve `503`,
  possibilitando o retry do provedor.
- A notificação pode vir sem `event` no payload LGPD, porque o Portal
  tem uma URL própria para cada tópico; se vier, o evento deve coincidir
  com a rota.
- Solicitação inicialmente de loja desconhecida gera alerta interno
  sem afetar outras lojas; caso o provedor reenvie após mapeamento
  correto, o evento será processado sem duplicar o protocolo.

## Efeito imediato e limites

**customer/redact**: ao receber evento autenticado de loja conhecida,
encerrar a adesão, desativar marketing e limpar nome/e-mail de
`ProgramParticipant` e `EnrollmentSubmission` relacionados ao
Customer (inclusive participantes legados sem `EnrollmentCustomerLink`).
Revogar desafios de e-mail abertos; manter auditoria do recebimento.

**app/store_redact**: suspender a loja, revogar a instalação OAuth
(tokens cifrados), tentativas OAuth e acesso de membros do tenant.
Preservar registros pendentes de revisão de eliminação conforme política.

**customers/data_request**: guardar solicitação mínima com ID de
pedido e Customer da mesma loja. A entrega do relatório de dados
à loja **não é automática nesta etapa**.

**ATENÇÃO — PRIVACIDADE NÃO ESTÁ CONCLUÍDA:**
- `202 Accepted` significa apenas **solicitação recebida e persistida**.
- Customer redact permanece `needs_review`; referência externa do
  cliente, eventuais lançamentos imutáveis e outras obrigações de
  retenção/eliminação exigem revisão e fechamento documentado.
- Store redact permanece `needs_review`; suspender acesso não equivale
  a excluir todos os dados da loja.
- Data request permanece `pending` até que relatório seja efetivamente
  preparado e enviado ao lojista, com evidência.
- Não marcar `completed` automaticamente nem afirmar atendimento
  integral à LGPD antes de criar e validar esse procedimento.
- Se houver retenção obrigatória de registros fiscais/financeiros,
  aplicar minimização e retenção apropriada com orientação jurídica.
- Backups, outros sistemas integrados e exclusão final ficam no runbook
  operacional que ainda precisa de implementação e revisão.
- A aprovação de novos participantes consulta pedidos de redaction
  pendentes e não permite reativar dados do consumidor afetado.

## Acompanhamento do lojista

Em **Configurações > Privacidade dos participantes**, proprietários e
administradores veem:
- total de solicitações em análise;
- quantidade de pedidos de acesso aos dados;
- quantidade de pedidos de exclusão;
- últimas solicitações, com tipo, data e status legíveis.

A API `GET /api/v1/tenants/{tenant_id}/privacy/requests/` usa
sessão autenticada, checagem de função e isolamento por tenant.
Nunca retorna ID do consumidor, e-mail, telefone, payload, segredo
ou identificador técnico de loja. Analista não tem acesso.

A administração interna do Django inclui `PrivacyWebhookRequest`
em modo **somente leitura**, disponível a superusuários. A
conclusão não pode ser inventada ou feita por uma ação genérica.

## Monitorar solicitações não atendidas

Dentro do container API:

```sh
python scripts/audit_privacy_backlog.py --hours 24
```

O comando retorna somente **contagens por tipo/status**, sem dados
pessoais. Exit code 2 indica solicitações abertas há mais de 24h.
Ainda **não** existe alerta/cron agendado automaticamente; configurar
monitor operacional aprovado antes de abrir para lojistas reais.

## Testes e critérios de publicação

- Django `test_privacy_webhooks.py`: assinatura, validação,
  rejeição de payloads inválidos, replay, reenvio de loja
  antes desconhecida, interrupção da participação, bloqueio de
  comunicação, isolamento da loja, revogação na exclusão da loja,
  erro de banco -> 503 e resumo do lojista sem PII.
- `test_customer_link_approval.py`: não aprovar participante
  com exclusão pendente.
- Playwright `store-settings.visual.spec.ts`: tela de privacidade
  no desktop/tablet/celular, sem vazamento de dados técnicos.
- CI do SHA exato: backend, frontend, QA visual, Compose, Docker,
  PostgreSQL separado e verificação de migração.
- Nova migração: `nuvemshop/0002_privacy_requests`.
- Credencial usada: `NUVEMSHOP_CLIENT_SECRET` já existente só
  no serviço API, não no worker ou frontend.

### Sequência de homologação ainda necessária

1. Revisar o commit atual no GitHub e a prova de sucesso do CI.
2. Fazer backup do PostgreSQL certo; migrar apenas homologação.
3. Confirmar domínio, TLS, proxy e segredo no ambiente sem imprimir valores.
4. Enviar casos **sintéticos assinados** no ambiente isolado, validar estados
   sem afetar nenhum cliente/loja reais.
5. Registrar as URLs no Portal de Parceiros após validação.
6. Implementar envio real do relatório e fechamento do procedimento
   de eliminação e retenção por cliente/loja **antes da ativação real**.
7. Só então validar ponta a ponta com autorização expressa e
   promover `main`, mantendo saldo/cashback desligados.

**Não feito nesta entrega:** cadastro no Portal, deploy Coolify,
uso de dados reais, exclusão total de PII, geração/envio completo
de relatório, alteração de `main`, cashback e leitura de pedidos.
