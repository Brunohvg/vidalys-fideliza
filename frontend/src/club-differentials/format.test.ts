import {describe, expect, it} from "vitest";
import {brl, dateBR, days, percent, points, ratio, whatsappShareUrl} from "./format";
import clubActive from "./fixtures/club-active.json";
import clubPreparing from "./fixtures/club-preparing.json";
import merchant from "./fixtures/merchant.json";

describe("formatação pt-BR (espelho de engine/formatting.py)", () => {
  it("formata moeda em centavos", () => {
    expect(brl(123456789)).toBe("R$ 1.234.567,89");
    expect(brl(5)).toBe("R$ 0,05");
    expect(brl(-100)).toBe("-R$ 1,00");
    expect(() => brl(1.5)).toThrow();
  });
  it("formata pontos, dias e datas", () => {
    expect(points(1)).toBe("1 ponto");
    expect(points(1500)).toBe("1.500 pontos");
    expect(points(1500, true)).toBe("1.500 pts");
    expect(days(1)).toBe("1 dia");
    expect(days(180)).toBe("180 dias");
    expect(dateBR("2026-11-23T15:00:00-03:00")).toBe("23/11/2026");
    expect(percent(0.3476)).toBe("34,8%");
    expect(ratio(3.46)).toBe("3,46×");
  });
  it("monta convite do WhatsApp sem dados pessoais", () => {
    const url = whatsappShareUrl("Loja", "https://x/clube/loja");
    expect(url.startsWith("https://wa.me/?text=")).toBe(true);
    expect(decodeURIComponent(url)).toContain("https://x/clube/loja");
  });
});

describe("contrato com o motor Python (fixtures gerados pelo backend)", () => {
  it("clube sem ledger não traz números", () => {
    expect(clubPreparing.ledger_active).toBe(false);
    expect(clubPreparing.balance).toBe(null);
    expect(clubPreparing.goal).toBe(null);
    expect(clubPreparing.rewards.every(r => r.state === "em_preparacao" || r.state === "indisponivel")).toBe(true);
  });
  it("clube ativo traz meta próxima e coerente com o saldo", () => {
    const goal = clubActive.goal!;
    expect(goal.points_cost - clubActive.balance!.available).toBe(goal.missing_points);
    expect(goal.progress_percent).toBeLessThan(100);
  });
  it("painel não afirma efeito sem amostra", () => {
    expect(merchant.health.lift!.status).toBe("dados_insuficientes");
    expect(merchant.health.lift!.difference).toBe(null);
  });
});
