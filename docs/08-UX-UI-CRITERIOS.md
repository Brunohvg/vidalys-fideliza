# Diretriz de Design — requisito P0

Versão 0.2, 10/11/2026. O visual é parte central do produto, não fase de acabamento.

## Direção visual
Vidalys Fideliza deve ser um SaaS moderno, muito claro, confiável e visualmente distinto. Manter identidade da família Vidalys; base grafite `#0B1120`, azul elétrico `#1263FF`, ciano `#00D1E6`, branco `#FFFFFF`, fundo `#F3F5F9`. Ciano é cor de acento, não cor principal de textos brancos. Manrope ou Inter como sugestões, sem distribuir fontes.

## Fluxos e telas obrigatórios para prototipação
1. Autenticação e onboarding de loja Nuvemshop.
2. Dashboard: saldo de benefícios emitidos/resgatados/pendentes, recompra e custo de campanha.
3. Programas e regras: modalidade, % ou pontos, teto, prazo, mínimo, público/categoria.
4. Simulador de impacto: venda, custo de produto informado/desconhecido, Pix, frete, desconto e cashback.
5. Clientes e carteiras: busca autorizada, extrato com estados, expiração e ajuste auditável.
6. Campanhas e histórico de eventos, erro de integração e permissões.
7. Área do comprador mobile: saldo disponível/pendente, validade, termos e resgate.
8. Painel do operador da plataforma (não confundir com admin do lojista).

## Fases visuais
**A. Experiência:** mapa de navegação, fluxos críticos, informações mínimas por tela.
**B. Layout:** wireframes e protótipos de alta fidelidade mobile + desktop, antes da implementação de telas comerciais.
**C. Sistema:** tokens de cor, tipografia, espaçamento, componentes, ícones, tabelas responsivas, gráficos, controles de foco e estados.
**D. Implementação:** React + TypeScript e integração apropriada; CSS encapsulado no widget da loja; sem alterar estilos do tema Ipanema.
**E. Auditoria:** screenshots reais em 390, 768 e 1440px, testes automatizados onde viáveis e revisão manual de conteúdo/contraste.

## Critérios de aceite por tela
- Interface mantém consistência de marca e hierarquia de informações (uma CTA predominante por contexto).
- Funciona a partir de 390 px sem rolagem horizontal e usa alvos de toque de pelo menos 44x44 px.
- Navegação por teclado, foco visível, contraste WCAG AA, labels de formulário, mensagens acessíveis e motion reduzido.
- Estados: loading, vazio, erro, sem permissão, sucesso, desabilitado, crédito pendente, expirado e estornado, conforme fluxo.
- Dados fictícios identificados como demonstração; dados reais só via API autorizada.
- Screenshots da UI real anexadas à entrega e comparadas com protótipo aprovado.
- Não utilizar Django Admin como interface final do lojista.

## Dual-brand
O painel do SaaS mantém Vidalys. A carteira/widget no e-commerce herda identidade validada da loja, com fallback acessível. Nenhum CSS global, mudança de preço visual ou script duplicado deve afetar seleção de variantes, Pix, frete ou carrinho.

## Gate obrigatório para o Codex
Na Fase 0, criar o pacote de design e pedir revisão antes do frontend comercial. A Fase 1 pode criar a fundação técnica em paralelo, mas sem aprovar UI improvisada como produto. Nenhuma publicação em produção antes de QA visual e funcional.
