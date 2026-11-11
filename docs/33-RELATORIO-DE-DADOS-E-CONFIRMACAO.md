# Relatórios de acesso e confirmação de recebimento — homologação

Data: 11/11/2026 · Código em `homolog` · Sem deploy nem uso de dados reais.

## Requisito e fonte

A Nuvemshop exige o webhook `customers/data_request` e indica que o app
deve fornecer ao **comerciante** um relatório sobre os dados pessoais que o
próprio app mantém. Fonte:
https://nuvemshop.dev/docs-api/resources/2025-03/webhook

Isso não autoriza enviar dados ao comprador sem comprovação adicional
da identidade. Nesta etapa o relatório é entregue apenas ao
**proprietário ou administrador autenticado da própria loja**, no
painel do Fideliza. O usuário deve confirmar explicitamente ter
recebido o arquivo. Esse aceite é uma declaração do lojista,
**não prova criptográfica de leitura por um terceiro**.

## Passo a passo do lojista

Em **Configurações > Privacidade dos participantes**, para um pedido
de acesso pendente:
1. Clicar em **Baixar relatório**. O navegador recebe arquivo JSON e
   não deixa sua cópia persistida no servidor. O lojista deve
   armazená-lo de forma protegida.
2. Revisar o relatório e a identificação do cliente.
3. Clicar em **Confirmar que recebi**. A API só aceita a confirmação
   com o hash SHA-256 da versão baixada e pelo **mesmo administrador
   autenticado** que realizou a geração.
4. Se os dados mudaram ou a identificação não está completa, a API
   devolve conflito e pede nova revisão. Nenhum pedido é
   encerrado automaticamente.

Sem confirmação, a solicitação permanece pendente. O resumo do
lojista mostra somente quantidades, tipo, data e status; **não**
mostra e-mail, nome, IDs de Customer, tokens ou escopos técnicos.

## APIs

- `GET /api/v1/tenants/{tenant_uuid}/privacy/requests/`:
  lista mínima dos pedidos pendentes, apenas owner/admin.
- `POST /api/v1/tenants/{tenant_uuid}/privacy/requests/{request_uuid}/report/`
  com corpo `{}`, cookie de sessão e cabeçalho CSRF:
  devolve `Content-Disposition: attachment` e JSON em memória.
  Cabeçalhos de controle: `X-Fideliza-Report-Digest` (SHA-256) e
  `X-Fideliza-Report-Complete` (`true` ou `false`).
- `POST /api/v1/tenants/{tenant_uuid}/privacy/requests/{request_uuid}/confirm/`
  com `{"confirm":true,"digest":"<sha256_do_arquivo>"}`:
  exige a mesma conta autenticada que baixou, digest igual ao atual,
  identificação suficiente, estado pendente e vínculo à mesma loja.
  Só então altera o protocolo para `completed`.

Os endpoints usam `Cache-Control: private, no-store`;
o conteúdo exportado não é salvo no banco nem em logs. O banco guarda
somente hash, ator responsável e timestamps. O relato de
confirmação permanece rastreável.

## Fontes de dados e cobertura

O relatório consulta apenas **dados internos do Vidalys Fideliza**,
nunca a base geral de clientes da Nuvemshop nem de outras integrações:

- Participações: status, nome, e-mail, aceite, regulamento e canal;
- Adesões ainda não vinculadas: consentimento, aceite de marketing,
  confirmação/retirada do e-mail e versão de regulamento;
- Relações entre aceite e participação;
- Movimentações internas de cashback, caso existam, com tipo,
  centavos, origem, regra e lançamentos, **sem afirmar
  pagamento, resgate ou nota fiscal**.

Não inclui `token_ciphertext`, senhas, `token_digest`,
`idempotency_key` ou dados de lojas diferentes.

Para identificar adesões ainda sem vínculo, o recebimento do webhook
calcula `HMAC-SHA256` do e-mail canônico com o segredo do aplicativo,
sem armazenar o e-mail no protocolo. Depois o relatório compara esse
HMAC exclusivamente com adesões do mesmo tenant. Se a mensagem
original não trouxe e-mail utilizável, o relatório fica marcado
**parcial** e a conclusão é bloqueada para revisão manual.
Se já houve exclusão do mesmo Customer, o relatório inclui
registros ainda retidos sob pseudônimo, mas também é marcado
**parcial**: aceitações que não tinham vínculo e tiveram o e-mail
apagado não podem ser reidentificadas com segurança. Nesses casos,
não se permite confirmar automaticamente o atendimento integral.

Limite por relatório: no máximo 1 MB e 2.000 movimentos internos;
volumes maiores são encaminhados para atendimento especial em vez
de entregar arquivo incompleto sem avisar.

**Rotação de segredo:** HMACs existentes dependem de
`NUVEMSHOP_CLIENT_SECRET`. Uma futura troca dessa chave precisa
de reconciliação dos protocolos pendentes ou do fluxo de atendimento
manual, já que não há e-mails em claro salvos na tabela de webhook.

## Exclusões e pseudonimização

Ao receber `customer/redact` válido, o Fideliza interrompe
comunicações, limpa nome/e-mail dos cadastros relacionados e
substitui as referências de Customer nos vínculos e participantes
por `anon:<hmac>` estável por loja. Os FKs internos continuam
válidos para auditoria e para evitar quebrar extratos.

**Pseudonimização não equivale a anonimização completa nem
eliminação definitiva.** O protocolo de exclusão permanece
`needs_review` enquanto existir retenção contábil, documentos,
backups ou referência residual. A leitura de pedidos e qualquer
recompensa real continuam desligadas.

O cliente que pediu exclusão não pode ser readmitido de forma
automática no programa apenas porque o pedido foi marcado
`completed`: um novo fluxo explícito de reautorização será
necessário.

## Validação

Cobertura de teste Django e Playwright:
- Sessão, CSRF, papel owner/admin e isolamento entre lojas;
- Relatório só da conta solicitada, incluindo adesões sem vínculo
  por HMAC, e dados de ledger da própria loja;
- Nenhum token, dado de outro tenant ou digest de desafio de e-mail
  no JSON;
- Digest SHA-256 do arquivo retornado, confirmação pelo mesmo usuário,
  reuso indevido e estado `completed` somente após aceite;
- Alteração dos dados após download exige gerar arquivo novo;
- Pedido sem identificação completa permanece pendente;
- Referências de Customer pseudonimizadas depois de redaction e
  bloqueio de reinscrição;
- Interface 390/768/1440px e fluxo de confirmação.

Migracão nova: `nuvemshop/0003_privacy_delivery_evidence`.

## Bloqueios de publicação

O código **não** foi instalado no Coolify por esta operação.
Continuam necessários: backup e migração do banco de homologação,
login de lojista de teste, SSL/CSRF e URLs de webhook cadastradas no
Portal de Parceiros, teste HMAC pela rede real sem PII e validação
jurídica da política de retenção e exclusão completa.

Não configurar cliente real, não executar redaction real, não
alterar `main` e não ativar cashback até homologação e autorização
específica.
