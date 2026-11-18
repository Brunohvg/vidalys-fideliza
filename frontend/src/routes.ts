/** One typed route contract shared by merchant and customer shells.
 * No authentication decision is made client-side: Django still validates sessions.
 * Cross-shell navigation uses a full load to prevent leaking merchant state.
 */
export type MerchantScreen =
  | "overview" | "clients" | "program" | "campaign" | "sales" | "settings"
  | "results" | "margin" | "costs" | "catalog";

export type ClubSection = "home" | "rewards" | "history" | "rules" | "profile";

export const merchantPaths: Record<MerchantScreen, string> = {
  overview: "/app/visao-geral",
  clients: "/app/clientes",
  program: "/app/programa",
  campaign: "/app/campanhas",
  sales: "/app/vendas",
  settings: "/app/configuracoes",
  results: "/app/ferramentas/resultados",
  margin: "/app/ferramentas/margem",
  costs: "/app/ferramentas/custos",
  catalog: "/app/ferramentas/conciliacao",
};

const pathToScreen = new Map<string, MerchantScreen>(
  Object.entries(merchantPaths).map(([name, path]) => [path, name as MerchantScreen])
);

const CLIENT_PAGE = /^\/app\/clientes\/([0-9a-f-]{36})$/i;

/** Página própria do cliente no painel: /app/clientes/<id>. Abre em outra aba com Ctrl/⌘. */
export function clientIdFromPath(pathname: string): string | null {
  const match = CLIENT_PAGE.exec(pathname.replace(/\/+$/, ""));
  return match ? match[1].toLowerCase() : null;
}

export function clientPath(id: string): string {
  return merchantPaths.clients + "/" + encodeURIComponent(id);
}

export function merchantScreenForPath(pathname: string): MerchantScreen | null {
  const clean = pathname.replace(/\/+$/, "") || "/";
  if (clean === "/app") return "overview";
  if (CLIENT_PAGE.test(clean)) return "clients";
  return pathToScreen.get(clean) ?? null;
}

export function isMerchantPath(pathname: string): boolean {
  return pathname === "/app" || pathname.startsWith("/app/");
}

export const merchantAuthPaths = [
  "/confirmar-conta", "/redefinir-senha", "/cadastrar", "/esqueci-senha",
] as const;

export function clubSlugFromPath(pathname: string): string | null {
  const match = /^\/clube\/([a-z0-9-]+)(?:\/(recompensas|historico|regras|perfil))?\/?$/i.exec(pathname);
  return match ? match[1].toLowerCase() : null;
}

const clubSegments: Record<Exclude<ClubSection, "home">, string> = {
  rewards: "recompensas", history: "historico", rules: "regras", profile: "perfil",
};

export function clubSectionForPath(pathname: string): ClubSection {
  const segment = pathname.replace(/\/+$/, "").split("/").at(-1);
  return segment === "recompensas" ? "rewards" : segment === "historico" ? "history"
    : segment === "regras" ? "rules" : segment === "perfil" ? "profile" : "home";
}

export function clubSectionPath(slug: string, section: ClubSection): string {
  const base = "/clube/" + encodeURIComponent(slug);
  return section === "home" ? base : base + "/" + clubSegments[section];
}

/** O link antigo de adesão (/participar/<loja>) agora abre o próprio clube. */
export function legacyJoinRedirect(pathname: string): string | null {
  const match = /^\/participar\/([a-z0-9-]+)\/?$/i.exec(pathname);
  return match ? "/clube/" + match[1].toLowerCase() + "#participar" : null;
}

export type EntryRoute =
  | "merchant" | "member" | "demo" | "merchant-auth"
  | "email-action" | "withdrawal" | "enrollment" | "marketing" | "not-found";

export function entryRoute(pathname: string): EntryRoute {
  if (pathname === "/demo") return "demo";
  if (pathname === "/") return "marketing";
  if (pathname === "/entrar" || pathname === "/entrar/") return "merchant";
  if (/^\/conhecer(?:\/(?:recursos|segmentos|integracoes))?\/?$/.test(pathname)) return "marketing";
  if (clubSlugFromPath(pathname)) return "member";
  const path = pathname.replace(/\/+$/, "") || "/";
  // Os links de confirmação têm tela própria; cadastro/reset solicitados
  // passam pelo MerchantAccess dentro do Portal com sessão preservada.
  if (path === "/confirmar-conta" || path === "/redefinir-senha") return "merchant-auth";
  if (path === "/cadastrar" || path === "/esqueci-senha") return "merchant";
  if (path === "/confirmar") return "email-action";
  if (/^\/retirar\/[a-z0-9-]+$/i.test(path)) return "withdrawal";
  if (path === "/participar" || /^\/participar\/[a-z0-9-]+$/i.test(path)) return "enrollment";
  if (isMerchantPath(pathname) && merchantScreenForPath(pathname)) return "merchant";
  return "not-found";
}
