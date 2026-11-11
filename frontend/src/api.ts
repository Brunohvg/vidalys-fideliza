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

async function writeJson<T>(method: "POST" | "PATCH", url: string, body: object): Promise<T> {
  const csrf = cookie("csrftoken");
  if (!csrf) throw new ApiError("Sessão de segurança não iniciada. Atualize a página.", 403);
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    body: JSON.stringify(body)
  });
  return readResponse<T>(response);
}

async function postJson<T>(url: string, body: object): Promise<T> {
  return writeJson<T>("POST", url, body);
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

export type CostReviewStatus = "missing_cost" | "needs_review" | "missing_price" | "ready_for_simulation";

export type CostItem = {
  id: string;
  reference: string;
  sku: string;
  external_variant_id: string;
  name: string;
  unit_cost_cents: number | null;
  selling_price_cents: number | null;
  provenance: string;
  verified_at: string | null;
  verified_by_name: string | null;
  version: number;
  review_status: CostReviewStatus;
  created_at: string;
  updated_at: string;
};

export type CostList = {
  summary: { total: number; missing_cost: number; needs_review: number; missing_price: number; ready: number };
  total_filtered: number;
  limit: number;
  offset: number;
  data_status: "manual_only";
  items: CostItem[];
};

export type CostItemInput = {
  reference?: string;
  name?: string;
  sku?: string;
  external_variant_id?: string;
  unit_cost_cents?: number | null;
  selling_price_cents?: number | null;
  provenance?: string;
  verify_cost?: boolean;
  expected_version?: number;
};

export type CostHistoryEntry = {
  action: "create" | "update";
  version: number;
  created_at: string;
  by: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown>;
};

export const merchantApi = {
  getSession: () => getJson<SessionInfo>("/api/v1/auth/session/"),
  listCosts: (tenantId: string, opts?: { q?: string; status?: CostReviewStatus | ""; offset?: number }) => {
    const path = "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/cost-items/";
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", "30");
    params.set("offset", String(opts?.offset || 0));
    return getJson<CostList>(path + "?" + params.toString());
  },
  createCost: (tenantId: string, data: CostItemInput) =>
    postJson<CostItem>("/api/v1/tenants/" + encodeURIComponent(tenantId) + "/cost-items/", data),
  updateCost: (tenantId: string, itemId: string, data: CostItemInput) =>
    writeJson<CostItem>("PATCH", "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/cost-items/" + encodeURIComponent(itemId) + "/", data),
  costHistory: (tenantId: string, itemId: string) =>
    getJson<{ item_id: string; history: CostHistoryEntry[] }>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/cost-items/" + encodeURIComponent(itemId) + "/history/"
    ),
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
