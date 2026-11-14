# Vidalys Fideliza — MVP comercial e experiência do cliente (v0.4)
**Revisão:** 14/11/2026 · **Branch:** `homolog`

## Decisão de produto

A operação do lojista deve caber em cinco lugares:
- **Visão geral:** três métricas realmente disponíveis e apenas uma próxima ação.
- **Programa:** recompensas, regra e adesão; um editor por vez.
- **Clientes:** ficha com identidade, consentimento, pontos registrados e histórico do balcão.
- **Vendas:** Nuvemshop e balcão separados; conferência operacional acessível a um só administrador.
- **Configurações:** OAuth, marca e privacidade em um só local.

Campanhas, análises e módulos por SKU ficam em **Mais ferramentas**, fora do fluxo principal.
Nunca exigir operador adicional só para conferir um recibo do próprio caixa:
owner/admin podem fazer autoconferência com justificativa, autor, data e estado
`self_review`. Essa confirmação **não prova captura independente** e **não gera pontos**.

## Referências verificadas de mercado

- **Smile.io:** visitante vê marca e recompensas; participante autenticado vê
  carteira, histórico e progresso; o catálogo é alimentado pelo mesmo programa
  que o lojista administra, sem conteúdo duplicado.
  https://smile.io/features/loyalty-landing-page
- **Fidelimax + Nuvemshop:** proposta comercial baseada em pedidos pagos,
  pontos automáticos e resgate por cupom da própria loja; o benefício útil
  exige fechamento de ciclo, não só uma tela de rascunho.
  https://www.fidelimax.com.br/integracoes/nuvemshop
- **DevHub Nuvemshop:** `NubeSDK` permite slots de UI e eventos em loja e
  checkout; `coupon:add` e `coupon:remove` são eventos somente no checkout.
  Esses eventos **não** substituem emissão idempotente de cupom nem conciliação
  de pagamento no servidor, e dependem da disponibilidade da integração.
  https://dev.nuvemshop.com.br/es/docs/applications/nube-sdk/events/overview
  https://dev.nuvemshop.com.br/docs

Não copiar layout/imagens/código das plataformas. Aplicar o padrão: **convidar,
acompanhar, resgatar** com identidade própria.

## Entregue em código nesta revisão (a validar no CI HEAD)

- Menu principal simplificado, ferramentas futuras recolhidas.
- Visão geral sem painel de promessas de IA nem números fictícios.
- Programa sem dois formulários longos simultâneos; benefícios primeiro,
  regras de acúmulo à parte e configurações centralizadas.
- Cliente com ficha detalhada baseada em dados da própria loja/tenant:
  consentimento, vínculo, saldo interno, compras manuais agregadas e pendências.
  Valores do caixa são **informados**, não receita PSP.
- Balcão funciona para equipe de uma pessoa: após registrar, vai ao histórico;
  proprietário ou administrador pode revisar sua própria venda com justificativa,
  e a API registra o modo `self_review`. Sem crédito automático.
- Página pública /clube/{slug}: hero personalizado, CTA de adesão,
  benefícios publicados visíveis também ao visitante, mesma fonte usada pelo
  participante; recompensa rascunho ou de outro tenant jamais é exposta.
- Página /participar/{slug}: formulário antes do texto longo;
  regulamento completo e aviso de privacidade acessíveis; opt-in de marketing
  continua independente. Nenhum benefício é prometido antes de ativação.
- CSS público refeito em estilos únicos, com foco em 320/390 px,
  sem camadas cumulativas de exceções.

## Condições para considerar o MVP **realmente funcional**

**Ainda não concluídas nesta revisão:**
1. **Pagamento autorizado:** Nuvemshop envia evento; processador recupera
   pedido pelo ID interno, valida tenant e opt-in e reconcilia captura
   financeira com provedor autorizado (ex.: Nuvem Pago/Stone), incluindo
   ajustes e chargeback. Status `paid` ou checkout concluído sozinho não
   comprova liquidação.
2. **Pontuação:** regra aprovada pelo lojista, cálculo em centavos com
   arredondamento documentado, crédito pendente idempotente, carência e
   liberação sob condições, vencimento e estorno/contestação reversível.
3. **Resgate:** saldo realmente utilizável, reserva atômica por lote,
   criação de cupom individual via API oficial Nuvemshop com escopo
   permitido/reconsentido, confirmação/expiração do cupom e rollback
   em falha e cancelamento. Não habilitar `write_coupons` sem contrato.
4. **Vitrine:** bloco de fidelização incorporado de forma autorizada à
   experiência da Nuvemshop, com benefício e saldo *reais*, sem quebrar
   carrinho, preço, frete, login ou seleção de variantes.
5. **Piloto:** com autorização específica, compra de teste → pagamento
   conciliado → pontos pendentes → liberados → resgate → cupom aplicado
   → compra posterior → cancelamento/estorno → saldo corrigido, comprovados
   por logs, banco e interface.

Uma simulação de pontos ou publicação informativa não atende a esses itens.
Não anunciar SaaS pronto para venda até o ciclo ser reproduzido.

## Segurança e operação

Dados limitados por tenant e participante com consentimento; cadastros de
compradores da Nuvemshop não viram opt-ins silenciosamente. Sem migrações ou
escritas financeiras novas nesta etapa; sem alteração de env para autoconferência.
Não tocar `main` nem a loja real durante UI/CI.
Implantar apenas SHA de `homolog` com CI verde, backup e teste do usuário na
instância Coolify; distinguir deploy de commit no GitHub.
