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

export type ProgramParticipant = {
  id: string;
  customer_reference: string;
  display_name: string;
  contact_email: string;
  status: "active" | "paused";
  consented_at: string;
  joined_at: string;
  last_program_activity_at: string | null;
  consent_channel: "customer_portal" | "storefront_opt_in";
  points_balance: null;
  cashback_balance_cents: number | null;
  cashback_pending_cents: number | null;
  cashback_reserved_cents: number | null;
  balance_status: "not_implemented" | "ledger_only";
};

export type CashbackWalletView = {
  mode: "ledger_read_only";
  balance_status: "not_implemented" | "ledger_only";
  balances: null | {
    pending_cents: number; available_cents: number; reserved_cents: number;
  };
  events: Array<{
    id: string; kind: "accrual" | "release" | "reserve" |
      "cancel_reservation" | "redeem" | "expire" |
      "reverse_pending" | "reverse_available";
    amount_cents: number; rule_version: string; created_at: string;
  }>;
  events_limit: 20;
  redemption_enabled: false;
  note: string;
};

export type ParticipantDirectoryResponse = {
  source: "verified_opt_in_only";
  data_status: "no_enrollment_channel";
  summary: { total: number; active: number; paused: number };
  total_filtered: number;
  limit: number;
  offset: number;
  items: ProgramParticipant[];
  note: string;
};

export type NuvemshopConnectionStatus = {
  configured: boolean;
  connected: boolean;
  store_id: string | null;
  scope: string | null;
  mode: "read_products_only";
  ready_for_write: false;
};

export type CatalogDecision = "matched" | "review_required" | "unmapped";
export type CatalogPreviewItem = {
  product_id: string;
  product_name: string;
  variant_id: string;
  sku: string;
  barcode: string;
  price_cents: number | null;
  promotional_price_cents: number | null;
  api_cost_cents: number | null;
  decision: CatalogDecision;
  match_type: "variant_id" | "sku_candidate" | "none";
  local_item_id: string | null;
  local_reference: string | null;
  local_cost_cents: number | null;
  local_verified: boolean;
  issues: string[];
  will_modify_cost: false;
  will_modify_product: false;
};
export type CatalogPreview = {
  mode: "read_only_snapshot_preview" | "read_only";
  source: "operator_supplied_json" | "nuvemshop_live_read_only";
  page?: number;
  empty?: boolean;
  automatically_approved: false;
  writes_performed: 0;
  summary: {
    products: number; variants: number; matched: number;
    review_required: number; unmapped: number;
    missing_api_cost: number; missing_sku: number;
  };
  items: CatalogPreviewItem[];
  warnings: string[];
};

export const merchantApi = {
  getSession: () => getJson<SessionInfo>("/api/v1/auth/session/"),
  listParticipants: (tenantId: string, opts?: {
    q?: string; status?: "active" | "paused" | "all"; offset?: number
  }) => {
    const query = new URLSearchParams();
    if (opts?.q) query.set("q", opts.q);
    if (opts?.status && opts.status !== "all") query.set("status", opts.status);
    query.set("offset", String(opts?.offset || 0));
    return getJson<ParticipantDirectoryResponse>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/participants/?" + query.toString()
    );
  },
  participantWallet: (tenantId: string, participantId: string) =>
    getJson<CashbackWalletView>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/participants/" + encodeURIComponent(participantId) + "/wallet/"
    ),
  nuvemshopStatus: (tenantId: string) =>
    getJson<NuvemshopConnectionStatus>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/nuvemshop/status/"
    ),
  beginNuvemshopOAuth: (tenantId: string) =>
    postJson<{ authorize_url: string; expires_in_seconds: number; mode: "read_products_only" }>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/nuvemshop/connect/", {}
    ),
  previewLiveNuvemshop: (tenantId: string, page: number = 1) =>
    getJson<CatalogPreview>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/nuvemshop/catalog/preview/?page=" + encodeURIComponent(String(page))
    ),
  reconcileCatalog: (tenantId: string, products: unknown[]) =>
    postJson<CatalogPreview>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/catalog/reconcile-preview/",
      { products }
    ),
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
