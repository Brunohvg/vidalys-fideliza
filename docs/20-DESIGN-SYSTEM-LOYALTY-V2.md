# Vidalys Fideliza — Design System v2

**Data:** 11/11/2026 · **Branch:** design/loyalty-experience-v2 · **Estado:** redesign proposto do portal Vidalys, não publicado. A identidade dos widgets nas lojas participantes deve herdar a marca do lojista.

## Conceito
O Fideliza não é um banco de pontos nem uma calculadora. É um sistema que cria **relacionamentos de recompra**, permite visualizar a **recompensa** e dá **confiança** ao lojista antes de liberar benefícios.

Arquétipo: **confiável, humano, claro, criterioso**. Priorizar legibilidade, bom espaçamento, cartões com informação útil e ações honestas. Evitar dashboard financeiro com dezenas de KPIs vazios, excesso de azul saturado, gamificação gratuita e gradientes em tudo.

## Paleta semântica oficial

| Token | HEX | Uso | Observação de contraste |
| --- | --- | --- | --- |
| ink | \`#10253E\` | Barra lateral, texto e confiabilidade | Melhor que preto puro |
| ink-soft | \`#233E55\` | Subtítulos/labels | Alto contraste em superfície |
| primary | \`#087F79\` | CTA e links, **relacionamento** | Branco sobre primary = **4,86:1** (AA para texto normal) |
| primary-hover | \`#096B66\` | Hover e foco | Branco = **6,35:1** |
| mint | \`#37D5BB\` | Progresso e detalhes sobre fundo escuro | NÃO usar como texto sobre branco |
| mint-soft | \`#E8F9F4\` | Fundo informativo e seleção | Exigir texto escuro |
| reward | \`#F5BA51\` | Recompensa alcançada, valor visual | NÃO usar como texto em superfície branca |
| reward-ink | \`#98631A\` | Títulos/ícones sobre fundo claro | Branco = **5,08:1** |
| reward-soft | \`#FFF6E6\` | Fundo de recompensa/atenção | Significado distinto de êxito |
| info | \`#2463BD\` | Dados técnicos e integrações | Branco = **5,84:1** |
| canvas | \`#F6F8FB\` | Fundo global com baixo ruído | — |
| surface | \`#FFFFFF\` | Cartões e áreas de trabalho | — |
| muted | \`#577085\` | Texto auxiliar | Branco = **5,17:1** |
| border | \`#DDE7EF\` | Bordas leves | Bordas não substituem rótulos |
| success | \`#167A56\` | Evento confirmado | Sempre ícone + texto |
| warning | \`#98631A\` | Revisão/orçamento em atenção | Sempre ícone + texto |
| danger | \`#AD334B\` | Falha/estorno/erro | Sempre ícone + texto |

**Jamais comunicar status só por cor.** Azul de integração, verde de aprovação, dourado de recompensa e âmbar de atenção são semânticos, não decoração aleatória.

## Tipografia e hierarquia
- **Manrope 600–800** para títulos (com fallback local para Inter/system-ui).
- **Inter 400–800** para campos, tabelas, textos e controles.
- Corpo de texto no geral 12–14px neste protótipo; próximo gate de acessibilidade deve elevar textos muito pequenos a 14–16px, conforme a interface real, e validar 200% de zoom.
- Títulos curtos, frases práticas e rótulos explícitos; não usar jargões técnicos como porta de entrada.
- Raio de cartões 16–22px; botões 11–12px, espaçamento generoso.

## Componentes estruturais
1. **Sidebar:** azul profundo, seleção marcada em menta, conteúdo principal claro.
2. **Cards de ação:** branco, ícones por natureza — conexão/relacionamento em verde, recompensa em dourado, informação técnica em azul.
3. **Campanhas:** wizard de três etapas com seleção e feedback, cálculo que explica hipóteses; análise financeira avançada sob demanda.
4. **Prévia de recompensa:** simulação de cartão digital do comprador com valor hipotético, sempre \`não resgatável\` e sem sugerir saldo real.
5. **Clientes:** lista de participantes opt-in, estado vazio real, sem número inventado de recompras.
6. **Resultados:** exibir indisponibilidade com contexto até existir evento financeiro e pedido pago verificável.
7. **Login:** marca consistente com aplicação; sem promessa de lucro garantido.

## Contrato funcional
- O estilo não altera contratos de API, OAuth, quotas, permissões, dados de clientes, estoque, pagamentos ou saldo.
- A prévia de carteira não tem botão de uso, não grava crédito e não foi publicada na loja.
- O widget e a carteira reais na vitrine devem adaptar branding do lojista (tema Ipanema ou outro) e cumprir contraste e responsividade, **não impor paleta Vidalys na loja**.
- Nunca confundir demonstração ou homologação com programa ativo.

## Testes/gates
- Testes automatizados de CSS semântico, login, navegação mobile e caminho campanha → prévia de recompensa em 390, 768 e 1440 px; sem overflow horizontal.
- Testes visuais Playwright e inspeção de capturas para verificar alinhamento, foco, contraste, estados de erro e cortes.
- Aprovação WCAG 2.2 AA como meta: contraste mínimo 4,5:1 para texto normal, 3:1 texto grande; controles com foco visível, rótulos e toque >=44px sempre que possível.
- Após revisão visual, levar para ambiente de homologação isolado via branch autorizada; **sem merge automático nem publicação na loja real**.

**Fonte CSS de execução:** \`frontend/src/fideliza-theme.css\` carregado após estilos antigos. \`brand/tokens.css\` é referência sincronizada no repositório. Ideal futuramente consolidar em pacote de design tokens versionado, para evitar deriva.
