# Carteira e ledger de cashback — primeira fatia funcional

**Escopo:** branch `feat/cashback-ledger-readonly-v1`, baseada no redesign
`design/loyalty-experience-v2`. **Nenhum benefício está ativo.**

## Implementado
- Carteira única por participante com consentimento validado, vinculada a um tenant.
- Centavos inteiros em BRL, eventos com chave idempotente e lançamentos
  de buckets `pending`, `available` e `reserved`.
- Serviço interno transacional com `select_for_update` no PostgreSQL,
  prevenção de saldo negativo e rejeição de repetição divergente.
- Endpoint de extrato restrito a membros da loja e listagem com saldo
  do ledger apenas quando houver carteira. Sem carteira = saldo desconhecido.
- Escrita **desabilitada por código** na configuração padrão. Não existe
  endpoint HTTP para concessão, reserva, resgate ou alteração de eventos.
- `ledger_only` significa saldo contábil interno, **não resgatável**.

## Operações internas modeladas (não ativadas)
- `accrual`: +pendente, após futura confirmação verificada de pagamento;
- `release`: -pendente +disponível, após regra de liberação;
- `reserve`: -disponível +reservado, após autorização de checkout;
- `cancel_reservation`: -reservado +disponível;
- `redeem`: -reservado, após pagamento do pedido que usa o benefício;
- `expire`, `reverse_pending`, `reverse_available`: contralançamentos.

**Limitação deliberada:** reembolso de valores já resgatados depende de
regra aprovada para recuperação, sem gerar saldo negativo. O serviço não
verifica webhooks, pagamentos, entrega nem estado de pedidos por si só.

## Consulta privada
`GET /api/v1/tenants/{tenant_id}/participants/{participant_id}/wallet/`

Exige sessão e vínculo de loja, não aceita participante com adesão retirada.
Sem carteira: `balances: null`, `balance_status: not_implemented`.
Com carteira: soma integral de lançamentos e últimos 20 eventos.
Sempre `redemption_enabled: false`. POST/PATCH retornam 405.

## Requisitos antes do piloto
1. Confirmar escopos e fluxo de eventos Nuvemshop com documentação atual.
2. Implementar pedido pago verificado, deduplicação, reconciliação e estornos.
3. Aprovar regras e versionamento de campanhas, validade, limites e orçamento.
4. Testar concorrência real no PostgreSQL, downgrade/reversão e carga.
5. Implementar autenticação do comprador, privacidade LGPD e POC de desconto.
6. Revisão fiscal e jurídica. Ativar somente por escopo explicitamente aprovado.

O ledger é **append-only via serviço de aplicação**, não uma garantia
de imutabilidade contra acesso direto privilegiado ao banco; proteger acesso
e avaliar restrições/triggers de banco antes da produção.
