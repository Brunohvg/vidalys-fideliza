/** One typed route contract shared by merchant and customer shells.
 * No authentication decision is made client-side: Django still validates sessions.
 * Cross-shell navigation uses a full load to prevent leaking merchant state.
 */
export type MerchantScreen =
  | "overview" | "clients" | "program" | "campaign" | "sales" | "settings"
  | "results" | "margin" | "costs" | "catalog";

export type ClubSection = "rewards" | "history" | "rules";

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

export function merchantScreenForPath(pathname: string): MerchantScreen | null {
  const clean = pathname.replace(/\/+$/, "") || "/";
  if (clean === "/" || clean === "/app") return "overview"; // legacy deep links
  return pathToScreen.get(clean) ?? null;
}

export function isMerchantPath(pathname: string): boolean {
  return pathname === "/" || pathname === "/app" || pathname.startsWith("/app/");
}

export const merchantAuthPaths = [
  "/confirmar-conta", "/redefinir-senha", "/cadastrar", "/esqueci-senha",
] as const;

export function clubSlugFromPath(pathname: string): string | null {
  const match = /^\/clube\/([a-z0-9-]+)(?:\/(recompensas|historico|regras))?\/?$/i.exec(pathname);
  return match ? match[1].toLowerCase() : null;
}

export function clubSectionForPath(pathname: string): ClubSection {
  const segment = pathname.replace(/\/+$/, "").split("/").at(-1);
  return segment === "historico" ? "history" : segment === "regras" ? "rules" : "rewards";
}

export function clubSectionPath(slug: string, section: ClubSection): string {
  const base = "/clube/" + encodeURIComponent(slug);
  return section === "rewards" ? base : base + (section === "history" ? "/historico" : "/regras");
}

export type EntryRoute =
  | "merchant" | "member" | "demo" | "merchant-auth"
  | "email-action" | "withdrawal" | "enrollment" | "not-found";

export function entryRoute(pathname: string): EntryRoute {
  if (pathname === "/demo") return "demo";
  if (clubSlugFromPath(pathname)) return "member";
  const path = pathname.replace(/\/+$/, "") || "/";
  if (merchantAuthPaths.some(page => page === path)) return "merchant-auth";
  if (path === "/confirmar") return "email-action";
  if (/^\/retirar\/[a-z0-9-]+$/i.test(path)) return "withdrawal";
  if (path === "/participar" || /^\/participar\/[a-z0-9-]+$/i.test(path)) return "enrollment";
  if (isMerchantPath(pathname) && merchantScreenForPath(pathname)) return "merchant";
  return "not-found";
}
