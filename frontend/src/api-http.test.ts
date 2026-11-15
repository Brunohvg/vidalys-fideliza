import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, merchantApi } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("contrato HTTP frontend x Django REST Framework", () => {
  it("mostra a mensagem específica do serializer em HTTP 400", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 400,
      json: async () => ({ existing_discounts_cents: ["Descontos acima do subtotal."] }),
    })));
    await expect(merchantApi.getSession()).rejects.toMatchObject({
      status: 400,
      message: "existing_discounts_cents: Descontos acima do subtotal.",
    });
  });

  it("normaliza falhas de rede em ApiError em vez de rejeições silenciosas", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Network error");
    }));
    await expect(merchantApi.getSession()).rejects.toMatchObject({
      name: "ApiError", status: 0,
    });
  });

  it("cancela fetch preso e devolve erro 408 para liberar loading", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) =>
      new Promise<never>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      })
    ));
    const result = merchantApi.getSession();
    const check = expect(result).rejects.toMatchObject({
      name: "ApiError", status: 408,
    });
    await vi.advanceTimersByTimeAsync(15_001);
    await check;
  });
});
