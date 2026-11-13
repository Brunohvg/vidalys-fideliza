# 43 — Vidalys Fideliza: roteiro de execução com gates e pendências

Atualizado em 11/11/2026. Fonte da verdade para a ordem de trabalho na
branch homolog. Não confundir código, CI, implantação e aprovação real.
A conexão Nuvemshop já disponível no ChatGPT não substitui a instalação
OAuth do aplicativo Fideliza no servidor de testes. Não usar TinyFish.

## Infraestrutura e contrato de variáveis

Uma única fonte Compose: compose.yaml, banco privado externo. Exemplo de
variáveis: .env.example. O painel Coolify continua sendo a fonte real dos
segredos; mudar o arquivo Git não altera Compose Location no servidor.
Conferir documentos 44 e 45 antes do Gate G1.

## Bloqueios globais

- Apenas a branch homolog. Main, produção e loja Bibelô preservadas.
- FIDELIZA_LEDGER_WRITES_ENABLED permanece False em código.
- PostgreSQL deve ser recurso externo privado, e credenciais da
  Nuvemshop somente no serviço API, não worker, frontend ou Redis.
- Qualquer chamada à Nuvemshop é só leitura, usando token próprio do
  app do Fideliza e da loja autorizada. Webhooks precisam HMAC.
- Eventos recebidos não provam pagamento independente. Nenhuma
  recompensa é concedida sem pagamento, identidade, regra, idempotência,
  orçamento e capacidade de estorno verificáveis.

## Protocolo de entrega e prova — obrigatório, para evitar trabalho circular

Esta página é a **única fonte de verdade do andamento**. O AGENTS.md
ordena aplicar este processo em toda tarefa nova. Não reabrir uma etapa
concluída por teste verificável nem acumular checklists paralelos.

**Estados padronizados (sempre separados):**
- **PENDENTE:** ainda não implementado/testado.
- **CÓDIGO VALIDADO:** SHA da homolog e CI/testes identificados.
- **HOMOLOGAÇÃO VALIDADA:** exatamente aquele SHA está em execução no
  Coolify, banco/serviços saudáveis e testes de runtime aprovados.
- **INTEGRAÇÃO REAL VALIDADA:** OAuth, SMTP, pedidos e demais operações
  necessárias passaram no provedor/loja de teste autorizados.
- **BLOQUEADO:** registrar dependência e ação de desbloqueio; não
  maquiar como concluído nem criar mais uma auditoria equivalente.

**Contrato de qualquer entrega:** gate Gx; estado anterior → estado
comprovado; SHA e CI (se mudou código); resultado do deploy e da
verificação (se existe); fluxo efetivamente exercitado; risco e bloqueio
restante; **uma única próxima ação executável**. Sem prova, manter
estado anterior. Não usar porcentagem como substituto dos gates.

**Regra de fluxo:** trabalhar no gate operacional mais antigo aberto.
Nenhum salto G1→G7 por conveniência. Se o gate depender de acesso
externo e ficar bloqueado, desenvolver offline apenas código isolado,
com rótulo CÓDIGO VALIDADO; nunca anunciar que foi homologado.
No máximo uma pendência operacional prioritária. Revisar alterações
de outros commits/agentes antes de escrever. Não recriar variáveis,
YAMLs, wizards, mecanismos de benefício ou documentos duplicados.

**Quadro de controle verificado em 12/11/2026:**

| Gate | Estado comprovado | Prova que falta | Próxima ação sem repetir trabalho |
| --- | --- | --- | --- |
| G0 (portal/UX) | CÓDIGO VALIDADO | Revisão visual no SHA publicado, mobile | Fazer junto ao smoke de G1 |
| **G1 (infra)** | **CÓDIGO RAW EM TESTES; HOMOLOGAÇÃO BLOQUEADA** | Managed reprovado no runtime; Raw com rotas e redes explícitas preparado, mas ainda sem prova do proxy/DB, backup/restore e deploy do SHA | **CI verde; conferir Traefik, rede Docker existente do DB, backup e opção Raw no Coolify antes de publicar** |
| G2 (OAuth) | CÓDIGO VALIDADO | Cinco configurações oficiais, loja piloto, escopos e GET real | Executar após G1 |
| G3 (adesão/SMTP) | CÓDIGO VALIDADO | SMTP real, consentimento, link de e-mail e vínculo único | Executar após G1/G2 |
| G4 (webhooks) | CÓDIGO VALIDADO | Registro e entrega HMAC em loja piloto, reenvio e ordenação | Executar após G2/G3 |
| G5 (reconsulta) | CÓDIGO VALIDADO | GET real, cancelamento e estorno sem crédito | Executar após G4 |
| G6 (benefício simulado) | CÓDIGO VALIDADO | UX e teto em homologação com dados sintéticos | Conferir na revisão do portal |
| G7 (conciliação financeira) | CÓDIGO OFFLINE EM TESTE: normalizador de capturas/reembolsos/chargebacks com idempotência; sem fonte PSP autenticada | Adaptador oficial, prova de captura/estorno, vínculo do pedido e reconciliação efetiva | Após G1–G5 reais, integrar PSP/ERP autorizado, validar margem e não abrir ledger antes de G8 |
| G8 (crédito/resgate) | PENDENTE (ledger bloqueado) | Ledger/idempotência/limites e reversões auditados | Não habilitar antes de G7 |
| G9 (gamificação) | PENDENTE | Níveis, missões, pontos, cupons e antifraude | Após G8; simulação isolada opcional |
| G10 (IA/multicanal) | PENDENTE | Integrações Flow/PDV, métricas confiáveis | Após validações de base |

### Evidência real do primeiro teste de G1 — 12/11/2026

Relato sanitizado de comandos executados **dentro do contêiner api**:
- audit_runtime_env: DATABASE_URL, DJANGO_SECRET_KEY, hosts, CSRF, DEBUG,
  SSL redirect, REDIS_URL e CELERY_BROKER_URL = OK (validação de
  estrutura/configuração, não teste de restauração nem prova de worker vivo).
- Django manage.py check = 0 problemas.
- Django showmigrations nuvemshop = [X] 0001 até 0006.
- NUVEMSHOP_OAUTH = DESLIGADO, recursos de cliente/pedido/email e ledger
  desligados, como esperado. Não habilitar ainda.
- SMTP_API_ISOLATION = FALHA: DEFAULT_FROM_EMAIL, EMAIL_HOST,
  EMAIL_HOST_USER e SERVER_EMAIL chegaram à API.
- LEGACY_ENV = ALERTA: SERVICE_PASSWORD_64_DJANGO presente na API.

**Hipótese ainda não verificada:** a configuração Compose efetiva do
Coolify diverge de compose.yaml atual, o contêiner não foi recriado após
atualização ou houve outra injeção de env. O Compose vigente declara
EMAIL_* e SERVICE_PASSWORD_64_DJANGO vazios na API. A precedência do
Docker Compose garante que environment explícito prevalece sobre
env_file. Não remover controles da auditoria nem inserir segredos
falsos para fazê-la passar.

**Ação focal de desbloqueio:** ver em Coolify (Application homolog)
qual foi o Compose realmente renderizado para o serviço api e seu
deploy/SHA; confirmar que os quatro nomes SMTP acima e
SERVICE_PASSWORD_64_DJANGO estão vazios na definição do serviço api
(sem mostrar valores), e corrigir divergência na definição efetiva ou
na injeção. Conservar configs SMTP somente no worker. Verificar backup
e restauração do banco independente ANTES de recriar contêineres ou
rotacionar segredos. Após corrigir: reiniciar/redeploy, executar UMA vez
o mesmo audit_runtime_env e seguir para teste de health/worker/backup.
Uma configuração OK não é evidência de serviço ou transação real.

Fontes operacionais: 
https://coolify.io/docs/applications/builds/docker-compose
https://docs.docker.com/reference/compose-file/services/

**Bloqueio conhecido de G1:** as variáveis Nuvemshop e a senha SMTP
do inventário compartilhado estavam vazias; a URL de banco e a chave
Django compartilhadas exigem rotação segura. Sem acesso autenticado ao
recurso do Coolify não há como verificar seu SHA ou backup; não afirmar
que G1 passou só porque GitHub Actions ficou verde.

**Não alterar a plataforma ou o banco por suposição.** Os critérios
de G1 exigem backup recuperável, proteção de segredos, conferência
da rede privada, Compose e SHA realmente publicados, auditorias
sanitizadas e healthchecks. Não usar TinyFish.

## Gates em sequência (não avançar o status sem evidência)

| Gate | Item | Código homolog | Evidência real ainda pendente |
| --- | --- | --- | --- |
| G0 | Identidade visual v2, navegação acessível e mobile | Implementado/testes automatizados | Revisão humana após novo deploy |
| G1 | Infraestrutura Coolify e DB externo seguro | Compose/CI isolado | SHA em execução, backup e restore testados |
| G2 | OAuth da Nuvemshop, escopos read_products, read_customers, read_orders | Implementado | Reautorização em loja piloto e GET externo comprovado |
| G3 | Regulamento, adesão, email verificado e vínculo automático | Implementado sob flags desligadas | Teste SMTP, consentimento, cliente exato e revogação |
| G4 | Inbox HMAC e deduplicação de order/paid e order/updated | Implementado sob flag desligada; timestamp opcional (migração 0006) | Eventos reais de piloto, duplicação e retenção |
| G5 | Inspeção de evento contra pedido atual, sem PII | Implementado sob flags de leitura | Testar na loja piloto, cancelamento, reembolso e manual |
| G6 | Simulador do motor de benefícios com CampanhaDraft existente | Implementado, não financeiro | Revisão de UX, regra e orçamento em homologação |
| G7 | Pedido financeiramente reconciliado, elegibilidade e estornos | **Parcial:** prévia compara total e valor pago reportado, sem provar captura | PSP ou ERP autorizado + contrato de conciliação e reversões |
| G8 | Versões de regra, orçamento atômico, ledger de concessão e resgate | Ledger interno sob bloqueio; motor real não implementado | Revisão LGPD/fiscal, antifraude, teste e autorização |
| G9 | Níveis VIP e missões, pontos e vouchers, indicação e brindes | Planejado | Implementação e testes com benefícios comprovados |
| G10 | IA com fallback, indicadores de retenção, canais Flow/PDV | Planejado | Integrações homologadas, sem presumir aumento de vendas |

A comparação parcial de valores no G7 apenas detecta divergência na Nuvemshop. NÃO dá crédito, não verifica PSP e não elimina os demais bloqueios.

O gate G6 é uma **simulação independente do financeiro**, por isso pode
ser construído enquanto G1–G5 aguardam acesso real. Isso não autoriza
pular G7 ou G8 para produzir benefício real.

## Entregas técnicas na sequência deste ciclo

- 40 — Webhooks assinados com inbox persistente, timestamp opcional, deduplicação e zero crédito.
- 41 — Reconsulta manual GET por UUID do evento recebido, reutiliza
  prévia de pedido, sem escrever no ledger.
- 42 — Motor puro de simulação conectado ao rascunho já existente:
  objetivos segunda compra, recorrência e reativação; orçamento e
  estimativa de cashback em centavos; zero recompensa real.
- Interface do lojista: teste de elegibilidade hipotética a partir da
  campanha salva, sem repetir cadastros e sem confundir com venda real.
- 46 — Leitura do campo de valor pago reportado pela Nuvemshop; divergência em revisão, nenhuma conciliação PSP concluída.
- Pré-voo: inclui estado da inbox, quantidade de eventos, inspeção
  habilitada, existência do simulador e gamificação ainda inativa.

## Teste de ponta a ponta indispensável após deploy (somente piloto)

1. Identificar SHA exato em execução e o banco exclusivo de homologação.
2. Verificar snapshot de backup e teste de restauração, sem expor secrets.
3. Rodar auditoria da env e pré-voo; conferir flags OFF de início.
4. Fazer login, navegar em mobile, salvar configurações e regulamento.
5. Testar convite, aceite voluntário, confirmação SMTP e vínculo exato.
6. Reautorizar OAuth oficial da loja de teste com os três scopes.
7. Enviar eventos HMAC reais e repetidos, confirmar isolamento e inbox.
8. Reconsultar pedidos de teste pagos, manuais, cancelados e reembolsados.
9. Salvar campanha, simular objetivo e teto; confirmar zero eventos de saldo.
10. Registrar divergências e corrigir antes de iniciar G7 (PSP).
11. Implementar e testar G7, depois G8 e por fim G9/G10.

## Não confundir

- Rascunho salvo não é campanha ativa.
- Cliente associado não tem compra comprovada.
- Webhook de pedido pago não é liquidação independente.
- Saldo simulado não é crédito pendente nem disponível.
- Missão/nível VIP projetado não é gamificação em produção.
- Job CI verde não é implantação Coolify nem teste com Nuvemshop real.

## Como verificar o pré-voo

No container API do Coolify homologado:

    python scripts/inspect_loyalty_journey.py --slug loja-piloto

Esse comando é somente leitura e usa o slug da loja de teste. Nunca
executar diretamente na produção para inferir recursos ainda não validados.

Referências: docs 35, 38, 39, 40, 41, 42 e página Notion 24.


## Progresso estimado para pilotos — 12/11/2026

**Estimativas operacionais, não progresso medido por tarefas concluídas:**
- Testes internos com clientes sintéticos: **~75%** de prontidão. Código
  implementado, CI e testes com DB descartável; não substituem deploy real.
- Piloto controlado de fidelização com **clientes reais**: **~45%**
  de prontidão. Demanda G1–G8 com evidência de pagamento, crédito,
  resgate e estorno; não iniciar promessa de recompensa antes disso.
- Produto completo com gamificação, multicanal e IA: **~35%**.
  G9/G10 permanecem conceituais ou documentados, não ativos.

As porcentagens representam julgamento técnico ponderado por risco,
não conclusão linear de G0 a G10 nem venda ou adoção comprovada.

**A ordem de teste em produção não muda:** (a) confirmar SHA publicado,
Compose e banco privado; (b) backup e restauração; (c) OAuth de loja
piloto e escopos; (d) SMTP e aceite LGPD; (e) webhooks assinados;
(f) leitura de pedidos/reembolsos; (g) PSP/ERP e identificação
verificados; (h) limite de orçamento, ledger, reversões e resgate;
(i) auditoria antes de envolver grupo voluntário real. Um piloto
somente de adesão, sem benefício financeiro, pode ser analisado
separadamente após G1–G3 e avaliação de privacidade, com comunicação
explícita de que cashback ainda não está disponível.

Reforço: sem acesso autenticado ao Coolify, os itens G1–G5 continuam
**pendentes de validação real**; CI verde não comprova implantação.


Atualização G1 12/11: a correção migrou o único Compose de Managed
para Raw e os testes passam a reprovar injeções globais. Não implantar
até conferir proxy Traefik e redes externas reais; ver docs/44.


**12/11/2026 — G7 independente de G1:** adicionada análise financeira
offline sem credenciais nem IO (docs/46); mantém provas de origem
independentes como pendência. A prioridade operacional segue G1 no
Coolify; nenhum gate financeiro foi liberado nem cliente real envolvido.

## Cadastro de lojistas, autenticação por e-mail e canais opcionais — 12/11/2026

**Decisão de produto:** Nuvemshop é um canal opcional. O lojista pode abrir conta, criar a loja interna e explorar planejamento/campanhas em modo seguro sem instalação OAuth. Integrações futuras por WhatsApp, Vidalys Flow e ponto de venda são arquitetura planejada, não sincronizações já disponíveis.

O login público deve usar **e-mail + senha**, preservando temporariamente username legado somente no backend e no Django Admin. O signup de lojistas é distinto da adesão de clientes dos programas. Criação automática do tenant ativo e membership OWNER ocorre **somente após confirmação de e-mail por token de uso único**; usuários novos nunca são staff/superuser. E-mail verificado tem unicidade case-insensitive por identidade normalizada, com rejeição a ambiguidades legadas. Senhas ficam apenas como hash. Recuperação usa novo desafio de uso único e respostas genéricas anti-enumeração; links usam fragmento de URL para não expor tokens em logs HTTP. Tokens expiram em 30 minutos.

A interface possui cadastro, login por e-mail, confirmar, reenvio, recuperar senha, redefinir senha e estados de erro. O Django Admin é interface **interna**, com URL `/admin/`; no proxy, `/admin` sem barra redireciona para `/admin/`. O superusuário NÃO é criado automaticamente nem sua senha é armazenada no repositório.

**Flag nova estritamente necessária:** `FIDELIZA_MERCHANT_SIGNUP_ENABLED` apenas na API, default 0; diferente de `FIDELIZA_PUBLIC_SIGNUP_ENABLED`, que controla a adesão de consumidores. Ambas dependem de e-mail confiável quando ativadas; `FIDELIZA_EMAIL_DELIVERY_ENABLED` tem o contrato único existente no worker. `FIDELIZA_LEDGER_WRITES_ENABLED=False` permanece em código.

**Pendente para homologação:** confirmar CI SHA e deploy real; revisar política de privacidade/termos do serviço para o lojista; validar SMTP do worker (o último relatório informou `EMAIL_HOST_PASSWORD` ausente); testar cadastro em caixa controlada e link real, login/logout/CSRF no navegador e migração do banco somente após backup existente. **Não ligar a flag de cadastro público antes desses itens.** No Coolify, somente após validação, `FIDELIZA_MERCHANT_SIGNUP_ENABLED=1` na API. O modo Raw, volumes e redes atuais devem permanecer.

**Próxima ação operacional única:** Work revisa o CI da branch homolog, publica o SHA aprovado em Raw e valida as rotas de autenticação (admin inclusa) sem ativar cadastro; em seguida, configura SMTP autorizado com teste de caixa controlada e só depois libera signup.



## Duplicidade de contas e identidade de lojistas (12/11/2026)

Proteção progressiva por **caixa de e-mail verificada**, não identidade civil. Além do e-mail normalizado, o servidor atribui a cada conta nova uma `MerchantEmailClaim` com índice `UNIQUE` no PostgreSQL. Para `gmail.com`/`googlemail.com`, normaliza alias de pontos e `+tag` para a mesma caixa; em outros provedores não presume regras iguais. Migração não destrutiva `core.0002_merchant_email_claim` reserva e-mails de contas existentes, sem excluir usuários ou consolidar lojas. O registro e a confirmação verificam contas antigas, inclusive usuários inativos e endereços ambíguos, evitando que um erro de login seja interpretado como e-mail disponível. Mesmo duas confirmações concorrentes não podem criar duas reivindicações para a mesma caixa. Rate limit do cadastro e recuperação usa a chave canônica. A solicitação de recuperação via alias só envia para o e-mail da conta confirmado.

Não é possível impedir totalmente a mesma pessoa de se cadastrar com dois e-mails independentes sem um segundo fator confiável (celular validado, documento etc.), e exigir documento sem necessidade aumentaria tratamento de dados pessoais. Produto previsto: um usuário pode acessar mais de uma loja usando vínculos específicos, sem registrar múltiplas contas.


## Identidade de e-mail profissional (12/11/2026)

O envio SMTP em produção do worker agora usa `EmailMultiAlternatives`: HTML com tabelas e estilos inline, espaçamento mobile, botão de ação e aviso antifraude, e versão de texto puro para clientes sem HTML. Os quatro eventos compartilham o **mesmo renderizador**: confirmação de lojista, recuperação de senha, confirmação de participação e confirmação de retirada. Nenhum novo domínio, provedor SMTP, variável ou pipeline de e-mails foi criado. Conteúdo dinâmico de nomes/lojas/URLs passa por escape HTML. O logo PNG existente do projeto é reutilizado como ativo estático público sob `/email-assets/vidalys-fideliza-logo.png`; se imagens externas estiverem bloqueadas no cliente, `alt` e todo o texto permanecem legíveis. Sem pixels de rastreamento.

**Publicação e prova pendentes:** novos e-mails só terão o design após o novo SHA ser publicado no Coolify Raw e o logo público responder HTTPS. Verificar o modelo HTML em Gmail e Outlook e o fallback texto sem vazar links/token. SMTP já foi testado pelo usuário para o template antigo; isso não comprova a aparência do novo template. Persistem os gates de confirmação do link, sessão/logout e recuperação real na homologação.


## G2 — Lojas sem canal e múltiplos cadastros (12/11/2026)

O primeiro cadastro de um lojista deve criar **um usuário**, **um Tenant próprio** e um vínculo OWNER, mas **nenhuma instalação de Nuvemshop**. Anteriormente o cadastro definia erroneamente `platform=nuvemshop`, confundindo o campo do admin com uma conexão OAuth real. A partir desta mudança, `Tenant.platform` inicia como `independent` (Sem integração), inclusive como default; o callback OAuth Nuvemshop aceita uma loja independente e só altera plataforma/ID externo após a troca segura do code e persistência do token cifrado. Lojas suspensas, tokens não autorizados, outras plataformas e reutilização da mesma loja externa continuam bloqueados.

A migração `tenants.0003` altera somente lojas geradas por **cadastro próprio e e-mail confirmado**, sem `external_store_id` e sem `NuvemshopInstallation`; não toca em integrações reais, lojas antigas sem prova nem dados financeiros. Django Admin mostra rótulo `Sem integração` para esse estado. A migração precisa ser executada após backup no PostgreSQL da homologação; o GitHub CI não prova o resultado do banco ao vivo.

**Duplicidade:** uma tentativa HTTP 202 não equivale a uma nova conta, e o sistema não envia outra confirmação para e-mail já registrado ou confirmação pendente. Isso é proposital para impedir enumeração; reenvio é explicitamente solicitado na tela, com limitação de frequência. Um e-mail verificado identifica uma conta. Para administrar várias lojas, a evolução correta é vincular mais Tenants ao mesmo usuário, não criar contas duplicadas.


## Visibilidade administrativa de cadastros pendentes (12/11/2026)

No Django Admin, o superusuário agora dispõe de **Cadastros de lojistas**, listagem somente de leitura com loja, e-mail mascarado, horário e estado `Aguardando confirmação`, `Confirmado` ou `Expirado`. Isso explica por que o Admin Usuários mostra somente uma conta após várias tentativas HTTP 202: solicitações pendentes ainda não são usuários. A página bloqueia inserção, edição e exclusão manuais para preservar a confirmação HMAC e evitar duplicação de tenants; não revela hash de senha ou token. Um operador não-superusuário não consegue abrir a listagem.


## G2 — Observabilidade de e-mails e incidente SMTP2GO (13/11/2026)

Diagnóstico na sequência de cadastros: uma resposta HTTP `202` pode não gerar nova tarefa quando já há conta confirmada, cadastro pendente ou cooldown. O worker observável anteriormente executou cinco mensagens em ~1–3 segundos, mas o SMTP2GO comunicou interrupção parcial em 12/11/2026, 21:30 UTC (Gmail/Outlook), explicando atrasos **após aceitação SMTP**. Não culpar Celery por atraso no provedor sem consultar os timestamps.

Implementação: nova tabela `EmailDispatch` guarda somente UUID de evento, referência técnica, categoria, estados e horários, sem dados pessoais/links/tokens. O envio de lojistas e participantes passa por um único `enqueue_email` após commit; se o Redis estiver indisponível, o evento é marcado `publish_failed` e identificado no admin. O worker faz reivindicação atômica, registra `sending` → `accepted`/`retry`/`failed`/`skipped` e não reenvia uma mesma tarefa concluída. Jobs legados sem ID continuam aceitos durante a implantação. Erros temporários têm até duas retentativas em 10/20s; erros permanentes falham sem duplicar tentativas. **Aceito pelo SMTP não significa entregue na caixa**. Confirme status no SMTP2GO Reports → Activity. No Django Admin, `Core → Disparos de e-mail` mostra tempo de fila e tempo SMTP, visível apenas para superusuário e sem permitir edição. A `core.0004_email_dispatch` exige migração em homologação; worker só inicia depois da API saudável e da migração.

Checklist operacional, sem mudar outros projetos: verificar SHA implantado, backup existente, `python manage.py showmigrations core`, worker `celery -A config inspect ping`, observar fila no admin, testar confirmação e redefinição com caixa de teste, comparar horários e buscar a mesma transação no SMTP2GO. Manter `FIDELIZA_PUBLIC_SIGNUP_ENABLED=0` e créditos financeiros bloqueados. Não adicionar Celery Beat, outros workers ou novas credenciais por este ajuste.

### Recuperação de falhas no cadastro repetido (13/11/2026)

No registro público por loja, a mesma caixa postal já pendente não cria outra
`EnrollmentSubmission`. Se houver desafio válido e a auditoria confirmar
`publish_failed`, `failed` ou `skipped`, uma nova tentativa de cadastro
pode publicar novamente **o mesmo desafio**, com cooldown de 180 segundos
por loja/e-mail e limite de três publicações por desafio. Eventos
`queued`, `sending`, `retry` ou `accepted` não são reenviados:
SMTP aceito pode estar apenas em atraso no SMTP2GO. Depois do vencimento,
pode ser emitido novo desafio, sem duplicar a adesão nem conceder crédito.

Estado: **código em homolog, aguardando CI do SHA final e deploy**. Essa
correção é independente do bloqueio de infraestrutura G1 e **não demonstra**
entrega real em Gmail/Outlook. Na verificação de G3, testar cadastro novo,
repetido com falha Redis sintética, duplicação bloqueada, mensagem aceita
pelo SMTP e confirmação única em ambiente de homologação.
