import type { MarginInput, MarginResult } from "./finance";

export type Store = {
  id: string;
  name: string;
  slug: string;
  status: "draft" | "active" | "suspended";
  role: "owner" | "admin" | "analyst";
};

export type SessionInfo =
  | { authenticated: false; user: null; tenants: [] }
  | { authenticated: true; user: { username: string; display_name: string }; tenants: Store[] };

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function cookie(name: string): string | null {
  const pair = document.cookie.split("; ").find(value => value.startsWith(name + "="));
  return pair ? decodeURIComponent(pair.slice(name.length + 1)) : null;
}

async function readResponse<T>(response: Response): Promise<T> {
  let body: unknown = null;
  try { body = await response.json(); } catch { /* error fallback */ }
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? String(body.detail)
      : "Não foi possível concluir a solicitação.";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "GET", credentials: "same-origin", cache: "no-store" });
  return readResponse<T>(response);
}

async function postJson<T>(url: string, body: object): Promise<T> {
  const csrf = cookie("csrftoken");
  if (!csrf) throw new ApiError("Sessão de segurança não iniciada. Atualize a página.", 403);
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    body: JSON.stringify(body)
  });
  return readResponse<T>(response);
}

export type CampaignPlanInput = MarginInput & {
  projected_paid_orders: number;
  campaign_budget_cents: number;
  already_committed_cents: number;
};

export type CampaignPlanResult = {
  mode: "planning_only";
  status: "cost_unknown" | "margin_already_below_target" |
    "budget_already_exceeded" | "cashback_exceeds_margin" |
    "campaign_budget_exceeded" | "within_limits";
  automatically_approved: false;
  projected_paid_orders: number;
  cashback_rate_bps: number;
  per_order_net_revenue_cents: number;
  per_order_cashback_cents: number;
  campaign_budget_cents: number;
  already_committed_cents: number;
  available_campaign_budget_cents: number;
  projected_new_exposure_cents: number;
  projected_total_exposure_cents: number;
  estimated_order_capacity: number | null;
  budget_within_limit: boolean;
  margin_within_target: boolean;
  maximum_margin_rate_bps: number | null;
  maximum_budget_rate_bps: number;
  suggested_limit_rate_bps: number | null;
  per_order_contribution_after_cents: number | null;
  projected_contribution_after_cents: number | null;
  warnings: string[];
};

export const merchantApi = {
  getSession: () => getJson<SessionInfo>("/api/v1/auth/session/"),
  login: (username: string, password: string) =>
    postJson<{ authenticated: true; tenants: Store[] }>("/api/v1/auth/login/", { username, password }),
  logout: () => postJson<{ authenticated: false }>("/api/v1/auth/logout/", {}),
  previewCampaign: (tenantId: string, input: CampaignPlanInput) =>
    postJson<CampaignPlanResult>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/campaign-plans/preview/",
      input
    ),
  simulate: (tenantId: string, input: MarginInput) =>
    postJson<MarginResult>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/margin-simulations/",
      input
    )
};
