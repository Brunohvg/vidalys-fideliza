import { describe, expect, it } from "vitest";
import { parseBrl, parsePercent, simulateMargin, type MarginInput } from "./finance";

function input(changes: Partial<MarginInput> = {}): MarginInput {
  return {
    eligible_subtotal_cents: 20000,
    existing_discounts_cents: 0,
    cost_of_goods_cents: 10000,
    payment_fee_cents: 500,
    shipping_subsidy_cents: 1000,
    other_variable_costs_cents: 500,
    proposed_cashback_bps: 200,
    minimum_margin_bps: 1500,
    ...changes
  };
}

describe("contrato do simulador financeiro", () => {
  it("repete o exemplo de margem do backend", () => {
    const r = simulateMargin(input());
    expect(r.estimated_cashback_exposure_cents).toBe(400);
    expect(r.contribution_before_cents).toBe(8000);
    expect(r.contribution_after_cents).toBe(7600);
    expect(r.margin_after_bps).toBe(3800);
    expect(r.safe_cashback_budget_cents).toBe(5000);
    expect(r.maximum_safe_cashback_bps).toBe(2500);
    expect(r.status).toBe("within_target");
    expect(r.automatically_approved).toBe(false);
  });
  it("inclui descontos existentes antes do cashback", () => {
    const r = simulateMargin(input({ existing_discounts_cents: 2000 }));
    expect(r.eligible_net_revenue_cents).toBe(18000);
    expect(r.estimated_cashback_exposure_cents).toBe(360);
    expect(r.contribution_after_cents).toBe(5640);
  });
  it("não informa margem segura sem custo", () => {
    const r = simulateMargin(input({ cost_of_goods_cents: null }));
    expect(r.status).toBe("cost_unknown");
    expect(r.margin_after_bps).toBeNull();
    expect(r.maximum_safe_cashback_bps).toBeNull();
  });
  it("bloqueia cashback que reduz margem abaixo da meta", () => {
    expect(simulateMargin(input({ proposed_cashback_bps: 3000 })).status).toBe("cashback_exceeds_margin");
  });
  it("bloqueia quando margem já está abaixo da meta", () => {
    expect(simulateMargin(input({ cost_of_goods_cents: 17500, proposed_cashback_bps: 0 })).status).toBe("margin_already_below_target");
  });
  it("arredonda crédito potencial sem usar float monetário", () => {
    const r = simulateMargin(input({
      eligible_subtotal_cents: 99, cost_of_goods_cents: 98,
      payment_fee_cents: 0, shipping_subsidy_cents: 0,
      other_variable_costs_cents: 0, proposed_cashback_bps: 100,
      minimum_margin_bps: 0
    }));
    expect(r.estimated_cashback_exposure_cents).toBe(1);
    expect(r.contribution_after_cents).toBe(0);
  });
  it("não aceita desconto consumindo todo subtotal", () => {
    expect(() => simulateMargin(input({ existing_discounts_cents: 20000 }))).toThrow();
  });
  it("converte BRL e percentual com precisão", () => {
    expect(parseBrl("200,90")).toBe(20090);
    expect(parseBrl("0.05")).toBe(5);
    expect(parseBrl("", true)).toBeNull();
    expect(parsePercent("2,25")).toBe(225);
    expect(() => parseBrl("-1")).toThrow();
    expect(() => parsePercent("120")).toThrow();
  });
});
