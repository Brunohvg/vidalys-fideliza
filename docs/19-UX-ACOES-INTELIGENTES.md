# Experiência do lojista v2 — Clientes, Campanhas, Resultados, Ações

**Status:** PR #11 em draft, branch feat/merchant-experience-clients-v1; empilhado sobre #10. Código da interface e da API sujeitos a homologação. **Não implantado no Coolify e não conectado a clientes reais da Bibelô.**

## Correção de direção do produto

O diferencial do Vidalys Fideliza não é pedir ao lojista que vire analista financeiro. É sugerir **a próxima melhor ação de recompra** com contexto e limites claros, e fazer o lojista aprovar cada ação. A versão anterior enfatizava Rentabilidade, Planejamento, Custo por SKU e Conciliação e escondia o valor central do programa.

Nova navegação principal:
1. **Visão geral / Ações** — próximos passos fundamentados no estado real do tenant, com justificativa; nunca apresentar opinião de IA como fato.
2. **Clientes** — base apenas de quem aderiu comprovadamente ao programa, não todos os consumidores da Nuvemshop. Adesão exige aceite explícito, versão de termos, origem e data.
3. **Campanhas** — fluxo guiado em três etapas: objetivo → parâmetros essenciais → prévia. Análise avançada de margem fica opcional e visível sob demanda.
4. **Resultados** — placeholders honestos até existirem eventos, pedidos e ledger válidos. Não atribuir recompras por proximidade de uma campanha.

Ferramentas avançadas: Rentabilidade, Custo por SKU (fallback opcional) e Conciliação (técnica).

## Clientes / participantes

- Modelo ProgramParticipant vinculado a tenant, external_customer_id, data e canal de aceite, versão de termos e status.
- API GET /api/v1/tenants/{id}/participants/ exige usuário autenticado e vínculo com tenant. Sem POST público, importação, opt-in falso, saldo inventado ou leitura de clientes externos.
- Campos points_balance e cashback_balance_cents são NULL e balance_status=not_implemented até existir ledger real.
- Clientes que revogaram a adesão não são considerados ativos e ficam fora da listagem de relacionamento comum. Regras de retenção/exclusão LGPD serão projetadas antes de ativar adesão pública.
- Nuvemshop OAuth atual tem SOMENTE read_products. Para leitura futura de contatos/read_customers e pagamentos/read_orders serão necessárias novas permissões autorizadas, minimização de dados e base legal. Não implementar sincronização sem isso.

## Campanhas simples sem enganar

A UI apresenta objetivos: segunda compra, reconquista, recorrência. Lojista escolhe taxa de cashback, orçamento mensal, ticket e volume de pedidos estimados, **valores hipotéticos**. Calcula apenas exposição ao benefício com valores em centavos: crédito por pedido e exposição total = crédito × pedidos projetados. **Não** prova margem segura, ganho de receita ou retorno financeiro. Não cria regra, orçamento reservado nem campanha ativa. O simulador avançado continua acessível para conferência com dados validados.

Quando houver dados reais: trazer ticket e volume de pedidos pagos (com janela de tempo explícita), custo por variante se disponível, taxas/frete/impostos conforme fontes confiáveis, nunca trocar NULL por zero. Custos ausentes podem ser complementados manualmente por item; não exigir cadastrar o catálogo inteiro antes de explorar o app.

## Ações Inteligentes: motor híbrido e transparência

**Neste PR o motor é determinístico e NÃO chama IA externa.** Recomendações iniciais baseiam-se somente no status da integração e na contagem de adesões do tenant. Ao não ter dados, sugere conectar a loja, preparar aceite e testar uma campanha. Quando não consegue buscar dados, mostra aviso de incompletude.

**Próximo módulo opcional:** interpretação com LLM, com Gemini como primeira escolha, e Grok como substituto configurável. O provedor de IA jamais ganha acesso às credenciais da Nuvemshop, PII de clientes, histórico de pedidos individualizados ou permissão de escrita. A validação financeira, os critérios de segmentação, os limites e o ato de conceder benefícios continuarão determinísticos no Django.

### Preço/API confirmado em 11/11/2026
- Gemini Developer API tem free tier para modelos selecionados, com limites variáveis; é **API**, não licença do chatbot. O conteúdo do nível gratuito pode ser usado pelo Google para melhorar produtos. Preços: https://ai.google.dev/gemini-api/docs/pricing ; limites: https://ai.google.dev/gemini-api/docs/rate-limits
- Grok chat gratuito não equivale à API; o Grok API cobra por tokens. https://x.ai/api e https://docs.x.ai/developers/pricing
- Não prometer uso ilimitado, preço zero em produção ou disponibilidade específica de modelo; confirmar no provedor ao ativar.

### Contrato de segurança antes de enviar dados para IA
1. **Disabled por padrão** e opt-in explícito do proprietário/admin da loja, com termo de tratamento por terceiro e informações de retenção.
2. Enviar apenas estatísticas agregadas não identificáveis e com limites mínimos de grupo; nunca e-mail, telefone, nome, CPF, endereço, número de pedido, SKU confidencial, token, dados fiscais ou texto livre copiado de clientes. Mesmo agregados pequenos podem reidentificar: não enviar grupos sensíveis/pequenos.
3. Dado de origem com período/denominador, consentimento verificável, moeda BRL e timezone configurado; separar pagamento criado, pago, entregue e recompra confirmada.
4. Servidor Django/proxy chama o provedor com chave de ambiente, **nunca** browser. Validar esquema JSON da resposta, sanitizar output, cotas por tenant, limites de tokens, timeout, retry proporcional, fallback do motor local e logs sem PII.
5. IA só produz rascunhos: sugestão, explicação, pressupostos e risco. **Não** publica campanha, gera cupom, envia WhatsApp/e-mail, altera clientes ou créditos. Toda ação passa por visualização de orçamento, regras e aprovação humana.
6. Em produção com dados reais, avaliar plano pago/termos de não treinamento antes de fornecer informações comerciais mais ricas, com revisão LGPD e acordos necessários.

## Diferencial de verdade (fases posteriores)
- Sugerir reativação por coorte e elegibilidade comprovada, não por geração livre.
- Prever exposição máxima de crédito, com teto por campanha e por cliente e margem validada.
- Mensurar segunda compra e recompra incremental, com grupo de comparação quando possível; explicitar limitações de atribuição.
- Carteira com ledger de crédito/resgate/estorno, reversão após reembolso e prevenção de duplicidades.
- Editor de campanhas acessível, feedback imediato, textos bons, contexto e estados vazios úteis, inspirado no design system Vidalys.

## Gate
Testes Django de tenant/consentimento/sem writes; UI Playwright 390, 768 e 1440 px, sem overflow; teste de campanha guiada e visibilidade de erro. Sem aprovação automática e sem deploy na main/Coolify pelo PR. Documentar screenshots reais de QA; não considerar design aprovado apenas porque compila.
