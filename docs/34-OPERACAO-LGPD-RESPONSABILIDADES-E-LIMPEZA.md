# Atendimento LGPD: responsabilidades e minimização automática

Referência: 11/11/2026 (America/Sao_Paulo). Aplicação Vidalys Fideliza,
branch `homolog`; **não publicada nem habilitada para pedidos reais**.

## Quem faz o quê

**Consumidor (titular):** solicita acesso, retirada do clube ou eliminação
dos dados. Não recebe permissão para alterar o banco do aplicativo.

**Lojista (controlador, em regra para o programa):** define a finalidade
da coleta e as instruções de tratamento; responde ao consumidor
sobre o resultado e sobre possíveis retenções legais. Deve publicar
um aviso de privacidade e oferecer um canal de solicitação.

**Vidalys Fideliza (operador, em regra nessa relação):** recebe os três
eventos oficiais da Nuvemshop, aplica as medidas de proteção no próprio
Fideliza, impede reativação indevida, mantém a trilha e entrega ao
lojista informações sobre conclusão ou retenção. O operador não deve
decidir sozinho pela exclusão de registros que a lei exija reter.
A Vidalys pode atuar como controladora de outros dados próprios
(por exemplo, faturamento e segurança do SaaS), conforme a finalidade.

**Nuvemshop:** responde pelos dados nos sistemas que ela controla,
nas finalidades e relações aplicáveis. O Fideliza nunca presume que
uma exclusão local afeta automaticamente a plataforma, o ERP ou outros
aplicativos.

Esta divisão precisa constar de contrato de tratamento entre
Vidalys e cada loja e ser revisada à luz do contexto concreto.

Fontes públicas:
- ANPD — https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados
- Nuvemshop — https://nuvemshop.dev/docs-api/resources/2025-03/webhook

## Execução automática no Fideliza

### 1. Exclusão de um consumidor — `customer/redact`

Recepção HMAC-SHA256 + registro idempotente por loja e Customer.
Dentro da transação:
- cancela desafios de e-mail;
- impede participação e mensagens de marketing;
- limpa nome e e-mail dos cadastros correspondentes;
- pseudonimiza o ID externo do consumidor nos participantes/vínculos;
- registra contagens e horário em `sanitization_summary` e
  `sanitized_at` **sem escrever o e-mail ou corpo do webhook**;
- mantém o protocolo `needs_review` quando existem dados residuais
  e obrigações de retenção.

**Não é exclusão completa de todos os bancos e backups.**
Referências em outros registros e histórico fiscal/financeiro
dependem de revisão. O próprio protocolo pode conter referência
ao Customer enquanto isso for necessário e lícito.

### 2. Desinstalação/exclusão da loja — `app/store_redact`

Imediatamente, no recebimento autenticado:
- suspende a loja;
- elimina tokens OAuth instalados e tentativas pendentes;
- remove acessos dos usuários à loja;
- registra o pedido e confirma recebimento.

Após o commit, um job Celery recebe **somente o UUID da solicitação**:
- cancela desafios de e-mail;
- desativa adesões, limpa contatos e proíbe marketing;
- pseudonimiza referências dos participantes e vínculos, preservando
  a integridade dos relacionamentos;
- remove identidade visual da loja, histórico de alteração da
  identidade, custos manuais e rascunhos de campanhas;
- mantém lançamentos do ledger, regulamentos/aceites e dados
  históricos necessários à revisão de retenção;
- grava exclusivamente contadores agregados e data de sanitização.

O job é idempotente, usa transação, retry/backoff e **não precisa
da credencial Nuvemshop no worker**, respeitando o isolamento do
Compose. A resposta HTTP não espera a sanitização de grandes bases.

O protocolo segue `needs_review`; não existe fechamento automático
das exclusões, pois retenção de dados e backups ainda precisam ser
auditados. Não afirmar eliminação integral ao lojista.

### 3. Garantias complementares

- Nenhum e-mail transacional do Fideliza é enviado após a loja
  ficar suspensa, mesmo que o job tenha entrado na fila antes do evento.
- Um link de confirmação emitido anteriormente não reativa
  adesão numa loja suspensa.
- Uma nova adesão do mesmo Customer é impedida enquanto o histórico
  de `customer/redact` exigir reavaliação.
- Os dados de uma loja não são modificados durante a limpeza
  de outra loja.
- O painel do lojista descreve o andamento em termos claros,
  sem variáveis, segredos ou IDs do titular.

### 4. Recuperação de fila e monitoramento

Se o Redis/Celery estiver indisponível depois que o webhook for
persistido, a limpeza não desaparece do banco:

```sh
# Somente consulta (sem enfileirar):
python scripts/dispatch_privacy_sanitization.py

# Reenfileira até 20 solicitações pendentes:
python scripts/dispatch_privacy_sanitization.py --limit 20 --enqueue

# Verifica se há casos abertos há mais de 24 horas:
python scripts/audit_privacy_backlog.py --hours 24
```

O comando só atua quando a instalação da loja já foi revogada e a
loja está suspensa. Não imprimir segredos nem dados de clientes em
contadores ou logs. A implantação deve ligar isso a monitoramento
operacional, **não a um botão do lojista**.

## Limites e decisões obrigatórias antes de produção

- Definir o papel jurídico de Vidalys e cada loja, as bases legais,
  o termo operador-controlador (DPA), políticas de retenção e SLAs.
- Estabelecer procedimento para fechamento de `needs_review`
  com prova específica de exclusão/retensão, incluindo backups.
- Não apagar extratos contábeis ou documentos fiscais sem
  analisar obrigação legal e referências cruzadas.
- Validar exclusão de loja e cliente com eventos de teste assinados
  no Coolify homologado e inspeção do banco **certo**.
- Verificar reenvios, interrupção do SMTP, fila Celery e o monitor
  de backlog sob carga representativa.
- Aprovar a política de privacidade real do lojista e publicar
  o canal de atendimento antes de ativar os webhooks.
- **Nenhum cashback, saldo, pedido ou API de escrita da Nuvemshop foi
  ativado neste ciclo.**

Migração: `nuvemshop/0004_privacy_sanitization_evidence`.
Novos módulos: `privacy_erasure.py`, `tasks.py` e
`scripts/dispatch_privacy_sanitization.py`.

Os registros de testes automatizados usam apenas dados sintéticos.
A branch `main`, o Coolify e a loja Bibelô não foram modificados.
