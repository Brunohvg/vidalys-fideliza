/**
 * Prévia LOCAL do simulador financeiro.
 * A API Django é a fonte de verdade para lojas autenticadas.
 * A UI demonstrativa não lê dados reais e não altera saldo ou cashback.
 * Contratos e casos de teste espelham backend/apps/margin/services.py.
 */
export type SimulationStatus =
  | "cost_unknown"
  | "margin_already_below_target"
  | "cashback_exceeds_margin"
  | "within_target";

export type MarginInput = {
  eligible_subtotal_cents: number;
  existing_discounts_cents: number;
  cost_of_goods_cents: number | null;
  payment_fee_cents: number;
  shipping_subsidy_cents: number;
  other_variable_costs_cents: number;
  proposed_cashback_bps: number;
  minimum_margin_bps: number;
};

export type MarginResult = {
  status: SimulationStatus;
  eligible_net_revenue_cents: number;
  estimated_cashback_exposure_cents: number;
  contribution_before_cents: number | null;
  contribution_after_cents: number | null;
  margin_after_bps: number | null;
  safe_cashback_budget_cents: number | null;
  maximum_safe_cashback_bps: number | null;
  minimum_margin_bps: number;
  automatically_approved: false;
};

const MAX_CENTS = 1_000_000_000;
export const brl = (cents: number): string =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(cents / 100);

export function parseBrl(raw: string, allowBlank = false): number | null {
  const value = raw.trim().replace(",", ".");
  if (allowBlank && value === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error("Informe um valor válido em reais (até 2 casas decimais).");
  const [integer, fraction = ""] = value.split(".");
  const cents = Number(integer) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(cents) || cents < 0 || cents > MAX_CENTS) {
    throw new Error("Valor fora do intervalo aceito.");
  }
  return cents;
}

export function parsePercent(raw: string): number {
  const value = raw.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error("Informe um percentual válido.");
  const bps = Math.round(Number(value) * 100);
  if (!Number.isInteger(bps) || bps < 0 || bps > 10000) {
    throw new Error("O percentual precisa estar entre 0% e 100%.");
  }
  return bps;
}

const roundBps = (cents: number, bps: number): number => Math.floor((cents * bps + 5000) / 10000);
const ceilBps = (cents: number, bps: number): number => Math.floor((cents * bps + 9999) / 10000);

function maximumSafeBps(net: number, budget: number): number {
  let lo = 0;
  let hi = 10000;
  while (lo < hi) {
    const mid = Math.floor((lo + hi + 1) / 2);
    if (roundBps(net, mid) <= budget) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export function simulateMargin(data: MarginInput): MarginResult {
  const money = [
    data.eligible_subtotal_cents, data.existing_discounts_cents,
    data.payment_fee_cents, data.shipping_subsidy_cents, data.other_variable_costs_cents
  ];
  if (data.cost_of_goods_cents !== null) money.push(data.cost_of_goods_cents);
  if (money.some(v => !Number.isSafeInteger(v) || v < 0 || v > MAX_CENTS)) {
    throw new Error("Valores monetários precisam estar em centavos válidos e não negativos.");
  }
  if (!Number.isInteger(data.minimum_margin_bps) || data.minimum_margin_bps < 0 || data.minimum_margin_bps > 10000 ||
      !Number.isInteger(data.proposed_cashback_bps) || data.proposed_cashback_bps < 0 || data.proposed_cashback_bps > 10000) {
    throw new Error("Percentuais inválidos.");
  }
  if (data.existing_discounts_cents >= data.eligible_subtotal_cents) {
    throw new Error("Os descontos existentes devem ser menores que o subtotal dos produtos.");
  }

  const net = data.eligible_subtotal_cents - data.existing_discounts_cents;
  const exposure = roundBps(net, data.proposed_cashback_bps);
  const base = {
    eligible_net_revenue_cents: net,
    estimated_cashback_exposure_cents: exposure,
    minimum_margin_bps: data.minimum_margin_bps,
    automatically_approved: false as const
  };
  if (data.cost_of_goods_cents === null) {
    return {
      ...base, status: "cost_unknown",
      contribution_before_cents: null, contribution_after_cents: null,
      margin_after_bps: null, safe_cashback_budget_cents: null,
      maximum_safe_cashback_bps: null
    };
  }

  const before = net - data.cost_of_goods_cents
    - data.payment_fee_cents - data.shipping_subsidy_cents - data.other_variable_costs_cents;
  const after = before - exposure;
  const floor = ceilBps(net, data.minimum_margin_bps);
  const budget = Math.min(net, Math.max(0, before - floor));
  const maximumRate = maximumSafeBps(net, budget);
  const status: SimulationStatus = before < floor ? "margin_already_below_target"
    : exposure > budget ? "cashback_exceeds_margin" : "within_target";

  return {
    ...base, status, contribution_before_cents: before,
    contribution_after_cents: after, margin_after_bps: Math.floor(after * 10000 / net),
    safe_cashback_budget_cents: budget, maximum_safe_cashback_bps: maximumRate
  };
}
