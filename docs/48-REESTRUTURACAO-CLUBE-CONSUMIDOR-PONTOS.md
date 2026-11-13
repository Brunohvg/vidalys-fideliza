# 48 — Reestruturação do Fideliza: Programa, Clientes, Meu Clube e pontos

**Data:** 13/11/2026. **Escopo:** `homolog`, sem deploy automático e sem
alterações na loja Bibelô, `main` ou ledger financeiro.
**Motivo:** revisão do fluxo real do lojista; cadastro e integração já
funcionavam, mas o produto confundia participantes, integrações e benefícios.

## Objetivo de produto

O cliente deve perceber um clube simples: aderir, confirmar e-mail, entrar
no próprio espaço, entender a regra, visualizar seus pontos e trocar por
recompensas efetivamente disponíveis. O lojista deve configurar o programa
uma vez e administrar **exceções**, não aprovar manualmente todos os membros
ou lançar pontos de cada compra.

A Nuvemshop é um primeiro canal, não uma exigência de adesão. Futuramente
cada empresa pode reunir Nuvemshop, PDV/loja física, WhatsApp (Vidalys Flow)
e outros canais na mesma identidade de participante, com evidências
criptográficas e proteção contra duplicidade. Não assumir que e-mails
parecidos ou mesmo nome são identidade única.

## Aprendizado com o mercado

- **Smile.io** organiza o programa por formas de ganhar e de usar pontos:
  https://faq.smile.io/en/articles/6380631-ways-to-earn-how-do-i-earn-points
- **LoyaltyLion** separa clientes, regras, recompensas, relatórios e recursos
  do cliente; mostra pontos por pedido e histórico:
  https://help.loyaltylion.com/en/articles/2064301-navigating-loyaltylion
  https://help.loyaltylion.com/en/articles/10044788-shopify-add-loyalty-to-your-customer-accounts
- **Yotpo** tem página de recompensas com adesão, login, progressão e resgate:
  https://support.yotpo.com/docs/creating-a-rewards-page
- **Fidelizar Mais/Fidelimax**, presentes no ecossistema Nuvemshop, reforçam
  demanda por pontos, fidelização e recompra:
  https://atendimento.nuvemshop.com.br/pt_BR/recursos-extras/como-instalar-e-configurar-o-aplicativo-fidelizar-mais
  https://atendimento.nuvemshop.com.br/pt_BR/marketing-e-comunicacao/como-integrar-o-fidelimax-na-minha-loja

**Diferença pretendida:** menos configuração duplicada, transparência do
valor do benefício e motor que não dependa do checkout de uma plataforma.

## Novo mapa de telas

### Painel do lojista
- **Visão geral:** metas, pendências e sugestões demonstráveis, sem declarar
  receita/ROI por simples proximidade de campanha.
- **Programa:** regulamento e privacidade, página/convites, solicitações
  excepcionais. Regras de pontos/recompensas aparecerão aqui apenas quando
  houver motor e contrato aprovados.
- **Clientes:** diretório, estado da adesão e histórico verificado.
  Não repetir formulários de termos, link de convite ou OAuth.
- **Campanhas:** ações planejadas de segunda compra, recorrência e recuperação.
- **Resultados:** só fatos atribuíveis e auditáveis.
- **Configurações:** identidade visual e integrações, exclusivamente.
- **Ferramentas avançadas:** rentabilidade e conciliação, sem misturar
  experiência operacional com cadastro de participantes.

### Cliente final — /clube/<slug>
- **Página pública:** marca da loja, explicação, regulamento e CTA aderir
  (quando a adesão pública estiver autorizada).
- **Entrar sem senha:** solicita link de 15 min para o e-mail já confirmado,
  mensagem neutra sem revelar se a conta existe; token HMAC único.
- **Minha conta:** nome, situação (aguardando/participando/pausado),
  regulamento e privacidade da versão aceita.
- **Meus pontos e recompensas:** vazios de forma explícita por ora;
  números e ações só surgirão após eventos financeiros verificáveis.
- **Histórico e suporte:** futuro extrato com aquisição pendente/liberada,
  estorno, expiração e resgate, além de contato da loja.

A sessão do consumidor não usa `TenantMembership` nem confere autoridade
de lojista. O identificador do participante jamais é fornecido pelo cliente
como parâmetro para obter saldo de outra pessoa. O endereço público é por
`slug`, mas dados pessoais só após link validado e consulta autenticada.

## Identidade e fluxo de adesão

1. Qualquer consumidor lê termos e privacidade e aceita voluntariamente;
   marketing é consentimento separado.
2. `EnrollmentSubmission` registra a versão aceita e gera confirmação
   de e-mail. Aceite isolado não prova identidade nem pagamento.
3. Após confirmação, modo independente opcional cria
   `ProgramParticipant` sem `external_customer_id`, sob transação,
   lock do tenant e proteção contra duplicações.
4. Quando autorizada, `read_customers` permite ligar o mesmo participante
   ao ID externo exato da Nuvemshop, sem duplicá-lo.
5. Loja física/WhatsApp usarão `SalesChannel` e identidades verificadas por
   canal, não campos extras repetidos em ProgramParticipant.
6. Retirada da adesão revoga participação e acesso ao clube. Dados financeiros
   auditáveis podem ter retenção obrigatória, sujeita à LGPD.

O toggle `FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED=0` é apenas proteção da
transição. Não torná-lo configuração repetida por lojista nem sobrepor
políticas existentes. Para habilitar em homologação, exige migração
`participants.0007`, e-mail transacional verificado, consentimento,
testes sintéticos e validação de cliente com e sem Nuvemshop.

## Futuro motor de pontos: contrato de compra

**Uma adesão não concede automaticamente pontos por compras antigas.**
Por padrão, somente compras elegíveis posteriores à adesão e à vigência da
regra geram pontos, salvo campanha retroativa expressa e auditável.

```
Participante ativo + identidade de canal validada
  → compra criada (ainda não gera pontos)
  → pagamento confirmado em fonte confiável
  → pedido normalizado e deduplicado por canal/referência
  → pontos PENDENTES na carteira
  → prazo de liberação e auditoria de devoluções
  → pontos DISPONÍVEIS
  → escolha de recompensa e reserva atômica
  → resgate aplicado de verdade no canal de venda
  → baixa definitiva e comprovante
```

### Proposta de regras configuráveis

- Regra inicial simples: `R$ 1,00 elegível = 1 ponto` como exemplo
  **não publicado**, com pontos em inteiros e valores monetários em centavos.
  Descontos, frete, tributos, gift cards e devoluções precisam de política
  explícita antes da implementação.
- Prova da compra não é `order/paid` isolado. Webhook assinado é gatilho;
  comparar pedido por GET oficial e conciliar pagamento, inclusive canais
  com confirmação manual, chargeback e reembolso.
- Uma compra gera **um único crédito** com chave de idempotência por
  empresa/canal/ID do pedido/versão da regra; eventos fora de ordem devem
  ser reconciliados antes de alterar saldo.
- Definir período de carência, vencimento, limite por cliente, orçamento
  e custo de recompensa, com alertas de margem e antifraude.
- Pontos e cashback em reais não são a mesma unidade/conta. Primeiro
  release comercial deve escolher **pontos como modalidade principal**.
- Catálogo futuro de recompensas: desconto fixo, frete grátis, brinde
  ou experiência, com disponibilidade real e custo limitado. Resgate
  deve ser integrado ao checkout/PDV/Flow, jamais cupom de fachada.
- O painel do cliente deve explicar claramente ganho, motivo do bloqueio,
  prazo de liberação/expiração e regras de troca.

## Status de implementação em 13/11/2026

**Código adicionado:** separação Programa/Clientes, abas de adesão, página
Meu Clube responsiva, API de acesso privado por e-mail e status protegido,
desafio de uso único, migração de membros independentes e serviço
opcional de criação após confirmação. Testes unitários e visuais adicionados.

**Pendente em runtime:** instalar nova revisão em Coolify Raw, confirmar
backup e migrações `core.0006` e `participants.0006/0007`,
verificar envio do link por SMTP e navegação de duas contas, ativar o
toggle independente somente em piloto autorizado e revisar os casos
de vínculo manual com plataforma. Não tratar CI como prova de e-mail real.

**Futuro:** regra de pontos com ledger próprio, pedidos pagos verificados,
motor de resgate, expiração, campanhas e integração multicanal. Não alterar
`FIDELIZA_LEDGER_WRITES_ENABLED` apenas para habilitar esses recursos.

## Referência MultiPlique/ApliqueMe — CPF e acesso seguro (13/11/2026)

Referências: https://multiplique.apliqueme.com.br/ e https://multiplique.apliqueme.com.br/regulamento
A landing divulga 1 ponto por R$ 1, níveis, troca de pontos por descontos, cupons por e-mail e indicação.
O regulamento menciona CPF para identificar compras. O primeiro acesso /signup solicita e-mail
no HTML público. Não foi possível validar o fator de autenticação de todas as telas: CPF como
identificador jamais equivale a senha ou prova de posse de identidade.

### Jornada desejada do Meu Clube

- Entrada simples **CPF ou e-mail**, seguida de confirmação de código/link no contato verificado;
- CPF serve para encontrar o cadastro ou uma compra, nunca para visualizar saldo/resgatar sozinho;
- Cadastro voluntário mantém consentimento e aviso de privacidade independentes de marketing;
- Participante possui ID interno estável por tenant, mesmo sem Nuvemshop;
- O login por e-mail já está no código de homologação. **CPF ainda NÃO está implementado.**

### Contrato de segurança e integração — FUTURO

1. CPF é dado pessoal (ANPD). Coletar apenas quando houver finalidade concreta e base legal,
   com minimização, retenção, controle de acesso e política revisada.
2. Ao coletar CPF, normalizar 11 dígitos, validar verificadores, mostrar só máscara. Usar
   HMAC com segredo servidor (pepper) e escopo por tenant para busca exata, jamais hash
   simples reversível por dicionário; criptografia autenticada apenas se a finalidade exigir
   recuperação do documento. CPF não deve ir a logs, URLs, eventos de analytics ou IA.
3. Limitar tentativas, usar respostas anti-enumeração e exigir autenticação temporária em
   e-mail/telefone já verificado para abrir saldo ou fazer resgate.
4. A API estável da Nuvemshop expõe contact_identification inclusive em pedidos de convidados:
   https://nuvemshop.dev/docs-api/resources/2025-03/order
   Isso pode apoiar vínculo com a compra, mas NÃO substitui prova de identidade nem status
   de pagamento confirmado. Identificação externa deverá ser por canal/empresa e auditável.
5. CPF divergente, duplicado ou ausente: não associar automaticamente nem creditar pontos;
   encaminhar para reconciliação protegida, sem vazamento de dados do titular.
6. Compras elegíveis somente após adesão e vigência da regra, salvo retroatividade explícita
   auditada. Estorno/reembolso e resgate devem ser idempotentes.

Não ativar coleta obrigatória de CPF nem acesso por CPF no Coolify antes dos testes LGPD,
fraude, autenticação e homologação com dados sintéticos.