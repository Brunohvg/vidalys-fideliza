import {describe, expect, it} from "vitest";
import {
  clubSectionForPath, clubSectionPath, clubSlugFromPath,
  entryRoute, merchantPaths, merchantScreenForPath,
} from "./routes";

describe("rotas públicas e privadas", () => {
  it("mantém / como alias e reconhece deep links de loja", () => {
    expect(merchantScreenForPath("/")).toBe("overview");
    expect(merchantScreenForPath("/app/vendas/")).toBe("sales");
    for (const [screen, path] of Object.entries(merchantPaths)) {
      expect(merchantScreenForPath(path)).toBe(screen);
      expect(entryRoute(path)).toBe("merchant");
    }
  });

  it("não entrega conteúdo do lojista em rotas desconhecidas", () => {
    expect(entryRoute("/app/nao-existe")).toBe("not-found");
    expect(entryRoute("/clube/loja/qualquer")).toBe("not-found");
    expect(entryRoute("/clube/loja-jardim/historico")).toBe("member");
    expect(entryRoute("/clube/loja-jardim/regras/")).toBe("member");
    expect(entryRoute("/confirmar-conta")).toBe("merchant-auth");
    expect(entryRoute("/participar/loja")).toBe("enrollment");
    expect(entryRoute("/demo")).toBe("demo");
  });

  it("separa seções do cliente da navegação da loja", () => {
    expect(clubSlugFromPath("/clube/loja-jardim/historico")).toBe("loja-jardim");
    expect(clubSectionForPath("/clube/loja-jardim/historico")).toBe("history");
    expect(clubSectionForPath("/clube/loja-jardim/regras")).toBe("rules");
    expect(clubSectionPath("loja-jardim", "rules")).toBe("/clube/loja-jardim/regras");
    expect(clubSectionPath("loja-jardim", "rewards")).toBe("/clube/loja-jardim");
  });
});
