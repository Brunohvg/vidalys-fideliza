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
| G7 (conciliação financeira) | PENDENTE (código preliminar de divergências) | Captura PSP/ERP independente, estorno parcial e total | Implementar após prova dos pedidos |
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
