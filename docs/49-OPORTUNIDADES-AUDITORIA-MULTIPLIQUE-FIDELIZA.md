# 49 — Oportunidades identificadas na auditoria MultiPlique

**Data:** 13/11/2026. **Fonte:** relatório do Work `Relatorio-Auditoria-MultiPlique-Vidalys-Fideliza.md` (248 linhas, auditoria somente leitura, conta de consumidor). **Destino:** `homolog`; nenhuma mudança em dados reais, pagamentos ou produção.

## 1. Classificação da evidência (não misturar)

| Evidência da auditoria | Categoria | Implicação para o Fideliza |
| --- | --- | --- |
| Dashboard com saldo zero, atalhos para prêmios/extrato/indicação, perfil e cartão/QR | Observado | Cliente precisa encontrar a própria carteira em uma página, sem conhecer a integração. |
| Catálogo com quatro opções de crédito, custo em pontos e bloqueio de resgate por saldo insuficiente | Observado | Benefício econômico e preço em pontos devem aparecer juntos, mas limite/validação final ainda requer teste. |
| Níveis com barra de progresso e categorias Prata/Ouro/Diamante | Observado | Gamificação útil, mas faixas e critérios não ficaram claros: só implementar depois do motor. |
| Indicação com QR, WhatsApp e e-mail; bônus de 300 pontos descrito | Interface e texto declarados | Referência de UX futura; não copiar valor de incentivo nem habilitar sem antifraude. |
| Login com campo CPF/CNPJ | Observado apenas o campo | Não foi verificado segundo fator; CPF identifica, **não autentica**. Usar OTP/link em contato previamente verificado. |
| Conversão 1 ponto/R$1 em página comercial e `XX` no regulamento | Declaração inconsistente | Publicar somente regras versionadas, completas, idênticas no site, onboarding, motor e extrato. |
| Crédito de pontos por compras pagas, estorno e resgate real | Não demonstrado | Não alegar fragilidade ou superioridade técnica sobre concorrente sem evidência. |
| Painel do lojista | Não acessível | Não afirmar que possui funcionalidades administrativas inferiores ou ausentes. |

## 2. Posicionamento do produto

**Proposta:** um clube de vantagens de implantação simples, orientado ao consumidor,
com pontos verificáveis e limite de custo para a loja, independente do canal de venda.

O ponto de entrada deve ser **Minha Loja → Programa**, sem exigir que o lojista
aprenda OAuth, event ledger, idempotência ou SKU antes de publicar um programa.
O backend implementa essas garantias e indica bloqueios apenas quando relevantes.

**Diferença comercial demonstrável a construir**, não promessa atual:
1. Consumidor: saldo disponível, pendente e a vencer; extrato explicativo e
   catálogo com valores reais, condições e resgate rastreável.
2. Lojista: "Conectar canal → Configurar regra → Revisar custo e margem → Publicar",
   com prévia do Meu Clube e do regulamento **sem placeholders**.
3. Operação: compra paga confirmada pela fonte, deduplicada por pedido/canal,
   pontos pendentes, carência, estorno e expiração comprováveis.
4. Multicanal: participante local e múltiplos vínculos externos verificados;
   mesma carteira para Nuvemshop, PDV/loja física, e Vidalys Flow no futuro.
5. Resgate apenas onde a recompensa possa ser realmente aplicada ao checkout,
   PDV ou atendimento, com reserva e reversão em falhas.

## 3. Evitar erro arquitetural

**Estado existente no código:** `CashbackWallet`, `CashbackEvent` e
`CashbackEntry` são ledger **em centavos de BRL**, idempotente e bloqueado
por `FIDELIZA_LEDGER_WRITES_ENABLED`. Não renomear esse saldo financeiro
em pontos, não multiplicar moeda por fator visual e não habilitar o flag
para simular implantação. Planejar carteira de pontos com **unidade distinta**
(e.g. entradas inteiras e snapshots da versão de regra), mantendo consistência
do ledger existente e testes de migração.

**Identidade:** `ProgramParticipant` já aceita ausência de
`external_customer_id`, e existe ativação standalone em flag desligado.
Antes de adicionar Flow ou PDV, normalizar vínculos por
`tenant + channel + store + external_customer_id`, cada um com tipo/fonte,
estado de verificação e auditoria de conflitos. Não converter CPF em senha
nem unir registros automaticamente apenas por nome ou telefone.

## 4. Roadmap recomendado — uma jornada de valor por vez

### P0 — piloto demonstrável e seguro

1. **Homologar acesso real:** publicar SHA aprovado em homologação com backup,
   migrações `participants.0006/0007` e `core.0006`; testar cadastro,
   confirmação, troca de sessão e entrada no Meu Clube usando SMTP real.
2. **UX essencial:** no Meu Clube, exibir adesão real, regulamento e estados
   vazios/pendentes sem números fictícios. No lojista, Programa/Clientes/
   Configurações separados, configuração em quatro passos e prévia pública.
3. **Contrato de pontos v1:** valor elegível, arredondamento, exclusões,
   carência, prazo, limite, devolução, chargeback e versão por tenant.
   Uma única modalidade de benefício principal na primeira versão.
4. **Prova de compra:** piloto Nuvemshop autorizado, `read_orders`,
   webhook verificado como sinal de releitura, consulta da API e status
   de pagamento. Sem crédito por mero webhook ou pedido criado.
5. **Ledger de PONTOS isolado:** crédito pendente/liberado, expiração e
   estorno, idempotência por canal/pedido/regra, testes de reenvio e corrida.
6. **Experiência do cliente:** carteira com extrato detalhado, pontos
   disponíveis/pendentes/a vencer e motivo de cada movimento.
7. **Uma recompensa real:** iniciar com uma opção controlada (desconto ou
   brinde conforme canal), reservar saldo, aplicar/confirmar, registrar
   recibo e compensar falha. Sem cupom fictício.

**Critério de aceite:** em loja piloto, um cliente aderente compra uma vez,
o pagamento é comprovado, os pontos são lançados uma única vez, liberados
após política, aparecem no Meu Clube e são resgatados em recompensa efetiva.
Reembolso estorna corretamente. Um segundo cliente ou loja não acessa saldo
alheio. Nenhum flag financeiro habilitado antes da aprovação desse ensaio.

### P1 — aquisição e gestão rentável

- Relatório comparável por período/coorte, custo efetivo dos benefícios e
  acompanhamento de recompras sem atribuição causal inventada.
- CPF **opcional** para localizar cadastro/venda presencial; OTP/link
  em canal de contato confirmado e minimização de dados conforme LGPD.
- Assistente de margem: alerta para benefício inviável com custos ausentes;
  orçamento máximo, exclusões, taxa de resgate e cenários.
- Recompensas adicionais: frete, brindes, acesso antecipado; estoque e
  condições comprováveis por canal.
- Identidade multicanal com exceções manuais auditadas; integração inicial
  com canal físico (não conectar Flow até contrato de identidade).
- Simplificação do dashboard: "participantes ativos", "pontos a liberar",
  "resgates", "custo do clube" e "próxima ação", sem elementos técnicos.

### P2 — diferenciais competitivos

- Indicação por QR/WhatsApp/e-mail, com antifraude e recompensa só após
  compra paga elegível do indicado.
- Níveis e missões com regras transparentes, budgets e proteção de margem.
- Vidalys Flow para convite, consulta segura e benefício do WhatsApp;
  consentimento de comunicação separado de adesão.
- Sugestões de campanhas baseadas em dados agregados, revisadas por humano,
  sem enviar PII para provedores de IA sem fundamento.

## 5. Antiobjetivos

- Não copiar interface, textos, ativos, dados ou caminhos privados do concorrente.
- Não inferir que CPF isolado é login inseguro no sistema concorrente: não testado.
- Não usar o valor de 300 pontos como incentivo padrão do Fideliza.
- Não introduzir configurações duplicadas nas telas de Clientes e Programa.
- Não manter placeholder `XX`, saldo fictício, benefícios não aplicáveis
  ou promessa de pontos para compras históricas por padrão.
- Não pedir CPF sem finalidade comprovada, sem controles LGPD e sem verificação.
- Não usar a carteira de cashback (BRL) como carteira de pontos.

**Referências de acompanhamento:**
`docs/43-ROADMAP-TESTES-E-PENDENCIAS-SEM-PULAR-ETAPAS.md`,
`docs/48-REESTRUTURACAO-CLUBE-CONSUMIDOR-PONTOS.md`,
`frontend/src/MemberClub.tsx` e `backend/apps/wallets/models.py`.
