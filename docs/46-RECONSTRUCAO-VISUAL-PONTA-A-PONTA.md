# Plano de reconstrução visual — Vidalys Fideliza

**Estado:** em execução; nenhuma etapa é considerada concluída sem evidência.
**Escopo:** exclusivamente experiência visual e usabilidade do site público, autenticação, painel do lojista, demonstração e clube do participante.
**Branch de referência:** `homolog`. Não publicar em produção, não ativar benefício financeiro, não alterar lógica de ledger, OAuth, integrações ou loja Nuvemshop.

## 0. Diagnóstico e fonte de verdade

Auditoria iniciada em 17/11/2026 a partir de cinco capturas enviadas pelo proprietário (painel real, demo, login, cadastro e landing page) e leitura do repositório.

Observações nas capturas:
- Excesso de áreas roxas/gradientes, com pouca distinção entre superfície, informação e CTA.
- Painel real: hero grande e genérico antes de indicadores e tarefas; dados e ações operacionais pouco destacados.
- Demo: navegação e distribuição dos cards diferentes do painel real, ainda que devessem ser variantes do mesmo produto.
- Login/cadastro: espaço publicitário desproporcional; presente cortado/sem acabamento; formulário poderia ter melhor distribuição e legibilidade.
- Site: cartões e seções repetitivas; quase nenhuma imagem concreta da experiência do produto; hierarquia comercial fraca.
- Marca: símbolo de sacola/presente e favicon precisam desenho vetorial consistente, opticamente legível em 16/32/48px.

Observações verificadas no código:
- `frontend/src/main.tsx` importa `styles.css`, `portal.css`, `fideliza-theme.css`, `experience.css` e `demo-theme.css`, sequencialmente; existem muitas regras sobrepostas e valores legados (azul, verde/jade e outras).
- `frontend/src/App.tsx` é a demo ilustrativa; `Portal.tsx` é a experiência do lojista. Não confundir os dois.
- `docs/05-IDENTIDADE.md` e `docs/08-UX-UI-CRITERIOS.md` descrevem paleta azul antiga, enquanto `fideliza-theme.css` usa navy/jade/mint; capturas mostram roxo/dourado. **A identidade aprovada precisa ser consolidada por tokens canônicos; não misturar legados.**
- A versão implantada no Coolify precisa ser comparada ao commit de `homolog` antes de atribuir visual do navegador ao código atual.

## 1. Direção de arte definida para a reconstrução

Manter Vidalys Fideliza identificável, mas tratar roxo como **cor de marca**, não como preenchimento de toda superfície.

### Tokens-alvo (propostos para revisão por contraste)
| Papel | Valor | Aplicação |
|---|---|---|
| Brand 900 | `#2B175B` | Navegação escura, títulos especiais |
| Brand 700 | `#4B279D` | Ações principais e links |
| Brand 500 | `#7445E8` | Acentos e estados ativos |
| Reward 500 | `#F6BB45` | Recompensa/ilustração; não texto pequeno sobre branco |
| Canvas | `#F7F8FC` | Fundo de aplicação |
| Surface | `#FFFFFF` | Cards, formulários, tabelas |
| Ink | `#211B33` | Texto principal |
| Muted | `#625B74` | Texto auxiliar, condicionado a WCAG AA |
| Border | `#E5E2EF` | Separadores suaves |
| Success | `#16744B` | Estados positivos |
| Warning | `#946000` | Alertas, com texto |
| Danger | `#B42336` | Erro/risco |

**Regras:** um CTA primário por contexto; gradiente apenas em hero/peça de marca, nunca como substituto universal de componente; tipografia Inter/Manrope com hierarquia clara; escala de espaçamentos 4/8/12/16/24/32/48; raios de 8–16px; ícones consistentes; superfícies com contraste real e sombras discretas. O clube de um lojista deve respeitar a marca da loja e oferecer fallback acessível, sem forçar a marca Vidalys.

## 2. Arquitetura CSS e componentes

- [ ] Inventariar seletores e cascata; separar legados por rota e eliminar duplicidade, sem apenas empilhar um sexto CSS global.
- [ ] Definir tokens únicos em arquivo de tema e documentar seus usos.
- [ ] Introduzir primitives reutilizáveis: `PageHeader`, `Card`, `Metric`, `Button`, `StatusBadge`, `Tabs`, `EmptyState`, `Alert`, `Table`, `FormField`, `Skeleton`.
- [ ] Garantir tokens sem vazamento para widget externo/tema Ipanema.
- [ ] Consolidar favicon e logo SVG em variantes escura, clara, horizontal e ícone pequeno; remover referências a símbolos legados depois de garantir que nenhuma rota os usa.
- [ ] Não modificar a lógica de autenticação, pedidos, permissão, finanças ou eventos ao refatorar componentes visuais.

## 3. Telas — definição de pronto

### Site público
- [ ] Hero distinto, proposição clara, mockups fiéis do produto, CTA e sinais de confiança verificáveis.
- [ ] Recursos, segmentos e integrações com informação concreta; não prometer canais não habilitados.
- [ ] Evitar repetição de blocos genéricos, gradientes e presentes.
- [ ] FAQ, rodapé, termos e rotas funcionais; mobile realmente pensado, não apenas comprimido.

### Login, cadastro, confirmação e recuperação
- [ ] Padrão de formulário unificado, labels/erros com acessibilidade, feedback claro.
- [ ] Ilustração e marca com acabamento; nada cortado involuntariamente.
- [ ] No cadastro, formulário priorizado; informar quando confirmação de e-mail é necessária.
- [ ] Não mostrar nem persistir valores sensíveis em capturas de QA.

### Painel real
- [ ] Dashboard compacto: participantes, pendências de conferência, recompensas, integração e próximos passos, todos com fontes reais e legenda de período.
- [ ] Revisar Clientes, Programa, Campanhas, Recompensas, Vendas e Configurações na mesma linguagem.
- [ ] Estados loading/vazio/erro/permissão e confirmação de ações destrutivas.
- [ ] Evitar métricas financeiras não verificadas e promessas de pontuação ativa.

### Demo
- [ ] Reutilizar layout, cards e navegação do painel real; separar dados pelo adaptador de demonstração, não por um design alternativo.
- [ ] Etiqueta DADOS FICTÍCIOS persistente e inequívoca.
- [ ] Preservar navegação de retorno e simulador, sem efeitos comerciais reais.

### Clube do participante
- [ ] Projetar mobile-first com benefícios disponíveis/publicados, regras, estado de pontos e histórico compreensíveis.
- [ ] Diferenciar saldo disponível, pendente, expirado e benefícios ilustrativos.
- [ ] Nunca expor dados de outro cliente; identidade do lojista respeitada.

## 4. Ordem de execução sem refazer trabalho

1. **Baseline:** verificar HEAD de `homolog`, SHA implantado, rotas e capturas em 390/768/1440px; congelar referência.
2. **Fundação:** consolidar tokens, fontes, ícones e componentes; migrar uma tela real como prova de conceito.
3. **Painel:** redesenhar dashboard, depois Clientes/Programa/Campanhas/Vendas/Configurações e recursos avançados.
4. **Público:** autenticação, site, segmentos, recursos e integrações.
5. **Demo:** usar o mesmo design system do painel real e conferir estados fictícios.
6. **Clube:** revisão de toda a jornada participante, com teste mobile.
7. **Limpeza:** remover overrides, classes e assets obsoletos; detectar regressões entre rotas.
8. **QA final:** teste automatizado, inspeção visual manual, acessibilidade, aprovação e só então deploy de homologação se gates operacionais permitirem.

## 5. Gates objetivos — necessários para fechar cada item

- `npm run build`, `npm test` e `npm run test:e2e` executados e resultados registrados (não presumir verdes).
- Screenshots comparáveis para cada rota principal em 390/768/1440px, com registro de diferenças.
- Sem overflow horizontal; controles interativos com pelo menos 44×44px; foco por teclado; contraste WCAG AA; estados carregando/vazio/erro.
- Verificar layout em dados longos, sessões expiradas, zero registros e API indisponível.
- Sem duplicação de tokens, scripts ou CSS conflitante; documentar exclusões de legado e possíveis exceções.
- Teste manual de login/cadastro, navegação e logout; componentes de vendas e recompensa continuam preservando regras de permissão e segurança.
- Para deploy: conferir backup/restauração e gates do `docs/43-ROADMAP-TESTES-E-PENDENCIAS-SEM-PULAR-ETAPAS.md`; **CI verde não é evidência de deploy.**

## 6. Diário de execução

| Data | Trabalho | Estado | Evidência |
|---|---|---|---|
| 17/11/2026 | Inspeção inicial das cinco capturas e estrutura CSS/React | Feito | Capturas fornecidas e `main.tsx`, `App.tsx`, `Portal.tsx`, `portal.css`, `styles.css`, `fideliza-theme.css`, `experience.css`, `demo-theme.css` lidos |
| 17/11/2026 | Especificação visual única e gates de reconstrução | Feito | Este documento |
| 17/11/2026 | Reconstrução integral de todas as rotas | Pendente | Não declarar concluído sem código, testes e capturas |
| 17/11/2026 | Deploy em homologação e QA real | Pendente | Gate operacional e SHA implantado ainda não comprovados neste trabalho |

**Regra de encerramento:** não confundir documentação/planejamento com interface reconstruída. Cada caixa só passa a marcada após alteração verificável, teste correspondente e evidência visual.
