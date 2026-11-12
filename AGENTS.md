# Regras persistentes para Codex — Vidalys Fideliza

## Objetivo

Infraestrutura vigente: apenas compose.yaml com PostgreSQL separado e
privado (docs/44). Cronologia de homologação: docs/43. Variáveis:
docs/45. Referências de Compose, escopos e paleta de versões antigas
no histórico abaixo não substituem o contrato vigente.
Criar um SaaS multi-tenant de fidelidade para e-commerce, inicialmente Nuvemshop, com pontos/cashback como crédito promocional, carteira auditável, métricas de recompra e custos. A Bibelô é a loja-piloto. É produto separado do Vidalys Flow.

## Fonte de verdade e precedência
1. Estado do código, testes e APIs Nuvemshop oficiais atualmente verificadas.
2. Documentação vigente deste repositório, especialmente `docs/01-PRD.md`, `docs/03-REGRAS-NEGOCIO.md`, `docs/04-ARQUITETURA.md`, `docs/05-IDENTIDADE.md` e `docs/08-UX-UI-CRITERIOS.md`.
3. Notion, como fonte editorial mais recente: https://app.notion.com/p/4148f612deaf8143b7d2c27f0623fa61 (se acessível; não pressupor conexão).
4. Registre conflitos e decida com aprovação humana; não assumir que hipótese comercial é regra aprovada.

## Diferencial competitivo obrigatório — margem primeiro
- Nosso posicionamento NÃO é "mais um app que gera cashback ou cupons".
- A diferenciação prioritária é **fidelidade com controle de margem e orçamento**, seguida de mensuração de recompra incremental.
- O simulador deve considerar descontos Pix, cupons, CMV por SKU, taxas, subsídio de frete e despesas variáveis; custo ausente nunca equivale a custo zero.
- Nenhuma simulação gera saldo, libera desconto ou ativa campanha. O lojista precisa de revisão financeira, confirmação dos dados e consentimento para ativação.
- Medir receita, margem e taxa de segunda compra com períodos comparáveis. Sem grupo controle ou método robusto, não alegar aumento causado pelo aplicativo.
- Evolução planejada: orçamento por campanha, limites por cesta/variante, detecção de combinação de promoções, cohort/holdout e benefícios alternativos de menor custo.
- Ver `docs/10-DIFERENCIAL-MARGIN-FIRST.md` e os testes de `apps.margin`. Não implementar IA de recomendação enquanto não houver dados confiáveis, feedback e limites.

## UI/UX é requisito P0, NÃO polimento posterior
- O produto deve ter qualidade visual profissional, distintiva e consistente com a marca Vidalys (navy, jade, mint e dourado do design v2 aprovado (docs/20)).
- Antes de implementar telas de negócio, criar mapa de navegação, wireframes, protótipos de alta fidelidade e componentes/tokens reutilizáveis. Requisito visual tem a mesma importância que testes financeiros.
- Django Admin é apenas ferramenta interna de suporte; NÃO é a interface comercial do lojista.
- Sem telas genéricas de template, paletas arbitrárias nem CSS global alterando o tema Nuvemshop.
- Widget do consumidor acompanha a identidade da loja conectada (Bibelô não herda paleta Vidalys).
- Cada tela deve ter estados loading/vazio/erro/sucesso, navegação por teclado, contraste WCAG AA, alvos de toque ≥44 px, screenshots reais em 390/768/1440 px e ausência de rolagem horizontal.
- Uma interface sem revisão visual e teste responsivo não está pronta, mesmo se os endpoints funcionarem.

## Stack recomendada
Django + DRF no backend; PostgreSQL; Redis/Celery para tarefas; React+TypeScript no frontend; Nube SDK/Nexo/Nimbus conforme suporte real; Coolify como hospedagem posterior. Monólito modular antes de microsserviços. Não adicionar Go no MVP sem problema mensurado.

## Segurança e transações
- `store_id` em todos os recursos e isolamento multi-tenant testado.
- Ledger imutável; créditos em centavos inteiros; regra e estornos versionados.
- Webhook recebido pode ser duplicado/fora de ordem: idempotência, fila e reconciliação.
- Reserva de cashback deve ser atômica; não debitar crédito em renderização de widget nem antes da confirmação prevista.
- Cliente anônimo não pode ver carteira de outra pessoa.
- Tokens e dados pessoais nunca entram em logs, commits, screenshots ou Notion.

## Escopo aprovado para o primeiro ciclo
Somente Fase 0 (validação técnica/documental, UX/UI) e fundação da Fase 1 (projeto, estrutura, testes e ambiente de desenvolvimento), separando a prova de conceito de descontos. Não instalar na Bibelô, publicar app, ativar benefício, alterar produção, editar Ipanema ou Vidalys Flow. Não usar credenciais reais sem autorização explícita.

## Protocolo obrigatório anti-retrabalho (aplica-se a TODAS as próximas tarefas)

A fonte única de andamento é docs/43. Antes de executar qualquer demanda:
1. Ler HEAD de homolog, resultado do CI desse SHA, docs/43, situação efetiva da homologação e últimos commits. Identificar mudanças feitas por outro agente antes de editar. Não recomeçar um recurso já implementado.
2. Escolher **um único gate desbloqueado** (G0–G10) e definir um resultado observável e critérios de aceite; vincular ao gate, não criar uma trilha paralela. Limite: uma prioridade operacional aberta de cada vez.
3. Usar quatro estados distintos e sempre reportá-los: **PENDENTE** (não implementado), **CÓDIGO VALIDADO** (commit + CI/testes), **HOMOLOGAÇÃO VALIDADA** (mesmo SHA executando, serviços/DB e testes no Coolify), **INTEGRAÇÃO REAL VALIDADA** (loja/PSP de teste e fluxo verificável). Opcional **BLOQUEADO** com dependência, responsável e teste exato que falta. Nunca elevar o estado sem evidência.
4. Cada alteração deve trazer o caminho de prova (commit SHA, job CI e conclusão, deploy SHA, comando/resultado sanitizado, fluxo testado, falhas) e um próximo passo acionável. CI aprovado NÃO equivale a publicação, OAuth funcional, SMTP entregue ou benefício real.
5. Fechar o gate só quando todos os critérios de saída forem demonstrados. Se faltar credencial, acesso, confirmação humana, backup ou consentimento, registrar **BLOQUEADO** e a ação externa específica. Não produzir outra auditoria, script, documentação ou flag para parecer progresso.
6. Quando um gate estiver bloqueado por terceiros, é permitido trabalhar no próximo item de código seguro **somente se for independente**, explicitando que ele continua CÓDIGO VALIDADO, sem pular critérios de homologação.
7. Manter um Compose único (compose.yaml), um modelo de env (.env.example) e um roteiro (docs/43). Não duplicar telas, regras, configurações, scripts de diagnóstico ou documentos. Alterar os arquivos existentes em vez de criar versões concorrentes.
8. Não expor ou reutilizar segredos compartilhados no chat. Rotação no provedor, backup antes de alterar BD, autorização explícita antes de alteração em infraestrutura, terceiros ou clientes reais. **Não usar TinyFish**. Não ativar ledger até pagamento, estorno, orçamento e resgate auditados.
9. No fechamento de cada tarefa, comunicar apenas: **gate atual, estado anterior → estado comprovado, evidência, bloqueio restante e próxima ação**. Não reiniciar o planejamento completo nem inventar percentuais novos sem critérios.

**Próxima prioridade operacional obrigatória:** G1 (Coolify + PostgreSQL privado + backup/restauração + SHA e env efetivos). Situação inicial: código/CI validados; runtime e backup ainda NÃO comprovados. Depois G2 OAuth, G3 adesão/SMTP, G4 webhooks, G5 leitura de pedidos, G6 simulação revisada, G7 conciliação PSP, G8 benefício real, G9 gamificação, G10 multicanal/IA. A ordem de gates e a segurança não são substituídas por novos commits de código.

## Processo para cada tarefa
1. Inspecione o repo, branch e documentos antes de escrever.
2. Apresente escopo curto, riscos e critérios de aceite antes de mudanças importantes.
3. Faça alterações pequenas e fáceis de revisar, com commits/PRs claros.
4. Execute os testes disponíveis e mostre resultado, screenshots e diffs; não invente evidências.
5. Liste pendências e próximos passos; peça autorização para alterações em sistemas externos/produção.


## Portal autenticado e tenant (P0)
- A rota / deve exigir sessão válida do Django. Apenas /demo pode mostrar exemplos fictícios.
- Todas as operações sensíveis pertencem a uma loja: verificar associação por usuário/tenant NO BACKEND, jamais confiar somente em seleção no frontend.
- Formulários mutáveis e login usam CSRF, sessão HttpOnly, HTTPS e limitação de tentativas; não criar senhas demo, credenciais em README nem token no frontend.
- A tela autenticada não apresenta métricas fictícias como se fossem reais. Dados sem integração devem exibir estado vazio ou indicação de funcionalidade em desenvolvimento.
- O simulador remoto não gera descontos nem salva dados; qualquer custo desconhecido continua sem indicação de margem segura.
- Validar desktop/mobile, estados vazios/erros/loading, acessibilidade e capturas antes de aprovar frontend. Referência: docs/11-PORTAL-LOJISTA-ACESSO.md.


## Planejamento de orçamento (prévia, sem ativação)
- Planejador de campanhas só calcula hipóteses em centavos e bps, nunca cria créditos.
- Sem dados de ERP/Nuvemshop, volume e custo são digitados manualmente e identificados como exemplos.
- O teto matemático combina orçamento restante e margem mínima, mas NÃO é recomendação comercial definitiva.
- Antes de habilitar campanha real: custos auditados, regras financeiras, ledger, API oficial Nuvemshop e testes de estorno/conversão.
- API tenant-scoped: conferir CSRF, autenticação, validação e isolamento. Ver docs/13-PLANEJADOR-CAMPANHAS.md.


## Cadastro de custos por SKU P0
- Custos de mercadoria são dados sensíveis por loja; armazenar por tenant, validar papel e versionamento.
- Não confundir SKU, referência local e ID de variante externa; custo não informado é NULL.
- Cadastro manual de custo inicia não conferido. Owner/admin pode conferir com evidência declarada; a conferência não substitui verificação do ERP.
- Edição de custo revoga confirmação. Nunca usar preços manuais como preços atuais da Nuvemshop sem revalidar.
- Registro versionado com histórico aditivo; nunca sobrescrever em lote ou aceitar um update com versão antiga.
- Não implementar conexão OAuth ou alteração de catálogo sem ler docs oficiais atuais e obter consentimento. Ver docs/16-CUSTOS-SKU.md.


## Conciliação do catálogo (prévia de amostra)
- Comparar product_id e variant_id antes de qualquer vínculo; alterações de atributos na Nuvemshop podem recriar IDs.
- SKU repetido, ausente ou candidato por troca de ID exige revisão humana. EAN não é chave de vinculação definitiva.
- Cost na API é opcional e não pode sobrescrever custo local conferido.
- API catalog/reconcile-preview/ exige login, tenant e limites estritos de payload; só faz leitura.
- Cliente GET oficial não tem token armazenado nem OAuth ativo. Ver docs/17-CONCILIACAO-CATALOGO.md.
- Nunca habilitar importação real nem cashback a partir desta prévia.


## OAuth Nuvemshop de leitura P0
- OAuth é iniciado pelo proprietário/admin autenticado na própria loja tenant, requer sessão + CSRF, HTTPS e state de uso único; não aceitar callback anônimo sem state.
- Authorization code expira em 5 minutos. Token pertence ao par app + loja, usa user_id como store ID e read_products para catálogo; read_customers e read_orders opcionais,
  independentes e somente após autorização/flags de homologação.
- Guardar somente token cifrado com Fernet em banco, com NUVEMSHOP_TOKEN_KEYS exclusivo da API em secrets Coolify. Nunca publicar chaves/token ou permitir secrets no worker/frontend.
- Rejeitar vinculação cruzada entre lojas; consulta GET da amostra usa store_id derivado da instalação autorizada, jamais parâmetro do cliente.
- Redigir logs de callback (Nginx e Gunicorn sem query); verificar proxy do Coolify.
- Nenhum write_products, read_orders, descontos, scripts ou cashback nesta etapa.
- Privacy webhooks, desinstalação e onboarding por App Store são gates antes de publicação; ver docs/18-OAUTH-NUVEMSHOP.md.


## Reorientação UX + ações inteligentes (PR #11)
- Fluxo do lojista começa em Ações → Clientes → Campanhas → Resultados. Ferramentas financeiras são avançadas e opcionais na interface.
- Listagem de participantes usa somente adesão com consentimento verificado; não chamar todos os clientes Nuvemshop de participantes. Não inventar saldos sem ledger.
- Cashbacks sugeridos no wizard são hipóteses, não recomendação financeira aprovada. Nunca inventar compras/receitas/ROI.
- Custo SKU manual é fallback quando Nuvemshop não informa cost confiável. Não exigir cadastro manual geral.
- Ações deste PR são regras locais sem chamada externa. Gemini/Grok são arquitetura futura opcional, default off; nenhuma PII/credencial para free-tier de IA, sem aprovação automática. Ver docs/19-UX-ACOES-INTELIGENTES.md.
