# Regras persistentes para Codex — Vidalys Fideliza

## Objetivo
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
- O produto deve ter qualidade visual profissional, distintiva e consistente com a marca Vidalys (grafite `#0B1120`, azul `#1263FF`, ciano `#00D1E6` apenas como acento).
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
