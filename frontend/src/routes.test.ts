import {describe, expect, it} from "vitest";
import {
  clubSectionForPath, clubSectionPath, clubSlugFromPath, legacyJoinRedirect,
  entryRoute, merchantPaths, merchantScreenForPath,
} from "./routes";

describe("rotas públicas e privadas", () => {
  it("reserva a raiz à apresentação e preserva deep links de loja", () => {
    expect(merchantScreenForPath("/")).toBeNull();
    expect(entryRoute("/")).toBe("marketing");
    expect(entryRoute("/conhecer")).toBe("marketing");
    expect(entryRoute("/entrar")).toBe("merchant");
    expect(entryRoute("/app")).toBe("merchant");
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
    expect(entryRoute("/redefinir-senha")).toBe("merchant-auth");
    expect(entryRoute("/cadastrar")).toBe("merchant");
    expect(entryRoute("/esqueci-senha")).toBe("merchant");
    expect(entryRoute("/participar/loja")).toBe("enrollment");
    expect(entryRoute("/demo")).toBe("demo");
  });

  it("separa seções do cliente da navegação da loja", () => {
    expect(clubSlugFromPath("/clube/loja-jardim/historico")).toBe("loja-jardim");
    expect(clubSectionForPath("/clube/loja-jardim/historico")).toBe("history");
    expect(clubSectionForPath("/clube/loja-jardim/regras")).toBe("rules");
    expect(clubSectionPath("loja-jardim", "rules")).toBe("/clube/loja-jardim/regras");
    expect(clubSectionPath("loja-jardim", "home")).toBe("/clube/loja-jardim");
    expect(clubSectionPath("loja-jardim", "rewards")).toBe("/clube/loja-jardim/recompensas");
    expect(clubSectionForPath("/clube/loja-jardim")).toBe("home");
    expect(legacyJoinRedirect("/participar/loja-jardim")).toBe("/clube/loja-jardim#participar");
    expect(legacyJoinRedirect("/participar")).toBeNull();
  });
});
