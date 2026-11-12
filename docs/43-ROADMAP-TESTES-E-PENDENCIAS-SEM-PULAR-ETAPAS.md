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
