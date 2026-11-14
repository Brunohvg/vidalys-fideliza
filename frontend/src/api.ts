import type { MarginInput, MarginResult } from "./finance";

export type PrivacyRequestsSummary = {
  pending_total: number;
  access_requests: number;
  deletion_requests: number;
  items: Array<{
    id: string;
    type: "data_access" | "deletion";
    received_at: string;
    status: "em_analise";
    protection_applied?: boolean;
    report_available: boolean;
    downloaded: boolean;
    can_confirm: boolean;
  }>;
  note: string;
};

export type TenantBranding = {
  program_name: string;
  primary_color: string;
  accent_color: string;
  support_email: string;
};
export type TenantPreferences = {
  tenant_id: string; tenant_name: string; tenant_slug: string;
  tenant_status: "draft"|"active"|"suspended";
  can_edit: boolean; version: number;
  branding: TenantBranding; public_link: null;
  features: {
    public_signup_enabled: boolean;
    email_delivery_enabled: boolean;
    customer_preview_enabled: boolean;
    cashback_activation_enabled: false;
    custom_domain_available: false;
  };
  note: string;
};
export type TenantPreferencesSaved = {
  version: number; branding: TenantBranding; updated: boolean;
};

export type Store = {
  id: string;
  name: string;
  slug: string;
  status: "draft" | "active" | "suspended";
  role: "owner" | "admin" | "analyst";
};

export type SessionInfo =
  | { authenticated: false; user: null; tenants: [] }
  | { authenticated: true; store_link_status?: "linked" | "missing";
      user: { username: string; display_name: string }; tenants: Store[] };

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


async function deleteJson<T>(url: string): Promise<T> {
  const csrf = cookie("csrftoken");
  if (!csrf) throw new ApiError("Sessão de segurança não iniciada. Atualize a página.", 403);
  return readResponse<T>(await fetch(url, {
    method: "DELETE", credentials: "same-origin", cache: "no-store",
    headers: { "X-CSRFToken": csrf }
  }));
}

async function postJson<T>(url: string, body: object): Promise<T> {
  return writeJson<T>("POST", url, body);
}

export type CampaignDraftInput = {
  title: string;
  goal: "second_purchase" | "reactivation" | "recurrence";
  cashback_rate_bps: number;
  ticket_cents: number;
  projected_paid_orders: number;
  budget_cents: number;
};

export type CampaignDraft = CampaignDraftInput & {
  id: string;
  version: number;
  status: "draft";
  created_at: string;
  updated_at: string;
  preview: {
    credit_per_order_cents: number;
    max_exposure_cents: number;
    exceeds_budget: boolean;
    assumptions_only: true;
  };
};

export type BenefitScenarioInput = {
  order_amount_cents: number;
  prior_paid_orders: number;
  days_since_last_paid_order?: number;
  committed_budget_cents?: number;
};

export type BenefitScenarioResult = {
  draft_id: string;
  draft_title: string;
  mode: "simulation_only";
  benefit_type: "cashback";
  goal: CampaignDraftInput["goal"];
  rule_version: number;
  state: "hypothetical_match" | "goal_not_met" | "budget_insufficient" | "reward_below_one_cent";
  goal_failure_code: string | null;
  hypothetical_goal_met: boolean;
  estimated_reward_cents: number;
  uncapped_reward_cents: number;
  remaining_budget_cents: number;
  forecast: CampaignDraft["preview"];
  activation_available: false;
  requires_verified_purchase_and_identity: true;
  requires_independent_payment_reconciliation: true;
  credit_eligible: false;
  ledger_writes_performed: 0;
};

export type CampaignDraftList = {
  mode: "draft_only";
  activation_available: false;
  items: CampaignDraft[];
};

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

export type DiscountRewardDraft = {
  id:string;title:string;points_cost:number;discount_cents:number;
  min_order_cents:number;max_redemptions:number;
  status:"draft"|"published";published:boolean;published_at?:string|null;
  redemption_enabled:false;
};
export type DiscountRewardDraftInput = Omit<DiscountRewardDraft,
  "id"|"status"|"published"|"published_at"|"redemption_enabled">;
export type PointCampaignDraft = {
  id:string;goal:"second_purchase"|"reactivation"|"recurrence";
  bonus_points:number;max_customers:number;maximum_bonus_points:number;
  status:"draft";published:false;sending_enabled:false;
};
export type PointCampaignDraftInput = Pick<PointCampaignDraft,
  "goal"|"bonus_points"|"max_customers">;

export type ManualSaleRecord = {
  id:string;channel:"counter";reference:string;participant_id:string|null;
  participant_name:string|null;eligible_amount_cents:number;reported_paid_at:string;
  evidence_reference:string;state:"awaiting_member"|"awaiting_review"|"verified_manual"|"rejected";
  created_at:string;reviewed_at:string|null;submitted_by_me:boolean;
  reviewed_by_me:boolean;review_mode:"owner_self_review"|"another_operator"|null;
  review_note:string|null;
  points_credited:false;cashback_credited:false;
};
export type ManualSaleInput = {
  reference:string;eligible_amount_cents:number;
  participant_id:string|null;reported_paid_at:string;evidence_reference:string;
};
export type ManualSaleList = {
  mode:"manual_review_only";points_credited:false;items:ManualSaleRecord[];
};
export type ManualSaleResult = {
  already_recorded:boolean;sale:ManualSaleRecord;
};
export type ManualSaleReviewResult = {
  sale:ManualSaleRecord;manual_evidence_reviewed:true;
  review_mode:"owner_self_review"|"another_operator";
  independent_payment_proof:false;points_credited:false;
};
export type PointRuleDraft = {
  version:number;points:number;per_cents:number;hold_days:number;validity_days:number;
};
export type PointRuleDraftResult = PointRuleDraft & {
  mode:"draft_only";activation_available:false;
  example_for_100_reais:number;points_credited:false;
};

export type ProgramParticipant = {
  id: string;
  customer_reference: string;
  nuvemshop_customer_linked:boolean;
  manual_sales_count:number;
  manual_sales_reviewed:number;
  manual_sales_pending:number;
  manual_sales_reported_cents:number;
  last_manual_sale_at:string|null;
  display_name: string;
  contact_email: string;
  status: "active" | "paused";
  consented_at: string;
  joined_at: string;
  last_program_activity_at: string | null;
  consent_channel: "customer_portal" | "storefront_opt_in";
  points_balance: number | null;
  points_pending: number | null;
  points_status: "not_active" | "ledger_only";
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

export type ProgramTerms = {
  id: string; version: string; title: string; body: string;
  privacy_notice: string; approved_at: string;
};
export type ProgramTermsStatus = {
  mode: "approval_required";
  public_signup_enabled: boolean;
  terms: ProgramTerms | null;
};
export type CustomerLinkApproved = {
  status:"linked"; already_linked:boolean; participant_id:string;
  cashback_enabled:false; orders_modified:false; message:string;
};

export type CustomerMatchPreview = {
  mode: "read_only_customer_match_preview";
  status: "one_exact_match" | "not_found" | "ambiguous";
  customer_id: string | null; email_verified: true;
  tenant_id: string; submission_id: string;
  scope_required: "read_customers"; writes_performed: 0;
  participant_created: false; cashback_enabled: false; note: string;
};

export type EnrollmentPending = {
  id: string; name: string; email: string; terms_version: string;
  accepted_at: string; marketing_opt_in: boolean;
  status: "pending_verification" | "email_verified";
};
export type EnrollmentPendingList = {
  mode: "consents_pending_identity_verification";
  total: number; items: EnrollmentPending[]; note: string;
};
export type InvitationCreated = {
  mode: "invitation_only"; token: string; expires_at: string;
  participant_created: false; cashback_enabled: false; note: string;
};
export type PublicInvitationPreview = {
  mode: "explicit_consent_only"; store_name: string;
  terms: ProgramTerms; expires_at: string;
  identity_verified: false; benefits_active: false;
};
export type PublicStoreProgram = {
  mode: "public_pre_enrollment";
  store_name: string; store_slug: string; terms: ProgramTerms;
  branding?: TenantBranding;
  identity_verification_required: true; benefits_active: false; note: string;
};
export type PublicStoreJoinResult = {
  status: "pending_verification"; participant_created: false;
  cashback_enabled: false; terms_version: string; message: string;
};
export type PublicConsentResult = {
  status: "pending_verification"; receipt_id: string; terms_version: string;
  participant_created: false; cashback_enabled: false; message: string;
};

export type ParticipantDirectoryResponse = {
  source: "verified_opt_in_only";
  data_status: "no_enrollment_channel" | "consent_verified";
  summary: { total: number; active: number; paused: number };
  total_filtered: number;
  limit: number;
  offset: number;
  items: ProgramParticipant[];
  note: string;
};

export type RecentOrdersPreview={
  mode:"read_only";source:"nuvemshop_live_read_only";
  items:PaidOrderInspection[];page:1;page_size:10;
  points_credited:false;coupons_created:false;read_only:true;note:string;
};

export type PaidOrderInspection = {
  order_id:string;order_number?:string|null;source:"nuvemshop_live_read_only";
  order_status:"open"|"closed"|"cancelled";
  payment_status:"pending"|"authorized"|"paid"|"partially_paid"|"abandoned"|"refunded"|"partially_refunded"|"voided"|"expired"|"chargeback";
  paid_at:string|null;reported_total_cents:number;currency:string;
  reported_customer_paid_cents:number|null;
  reported_payment_differs_from_total:boolean|null;
  reported_paid_amount_is_not_psp_proof:true;
  participant_verified:boolean;
  review_status:"blocked_cancelled"|"blocked_refund"|"blocked_chargeback"|"not_paid"|
    "payment_date_missing"|"customer_not_verified"|
    "manual_payment_review"|"reported_paid_amount_review"|
    "reported_paid_requires_reconciliation";
  credit_eligible:false;cashback_created:false;writes_performed:0;
  note:string;
};

export type NuvemshopConnectionStatus = {
  configured: boolean;
  connected: boolean;
  order_verification?: {
    order_scope_granted:boolean;
    preview_enabled:boolean;read_only_preview_available:boolean;
    live_cashback_enabled:false;signed_event_inbox_enabled:boolean;
    event_receipt_does_not_verify_payment:true;
  };
  connection_check?: {
    next_step: "activate_tenant" | "configure_app" | "authorize_store" |
      "grant_read_products_and_reinstall" | "verify_catalog_with_live_get";
    installation_recorded: boolean;
    catalog_scope_granted: boolean;
    live_access_checked: false;
    live_access_check_available: boolean;
    permissions_must_be_changed_in_partner_portal: boolean;
    reinstallation_required_after_scope_change: boolean;
  };
  store_id: string | null;
  scope: string | null;
  mode: "read_products_only";
  ready_for_write: false;
  customer_matching?: {
    preview_enabled: boolean;
    customer_scope_granted: boolean;
    read_only_preview_available: boolean;
    participant_approval_available?: boolean;
    automatic_linking_available?: boolean;
    requires_partner_portal_scope_and_reinstallation: boolean;
    will_activate_participants: false;
    will_credit_cashback: false;
  };
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
  listDiscountRewardDrafts:(tenantId:string)=>getJson<{
    mode:"draft_only";activation_available:false;items:DiscountRewardDraft[]
  }>("/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/reward-drafts/"),
  saveDiscountRewardDraft:(tenantId:string,payload:DiscountRewardDraftInput)=>
    postJson<{mode:"draft_only";reward:DiscountRewardDraft;coupon_created:false}>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/reward-drafts/",payload),
  updateDiscountRewardDraft:(tenantId:string,id:string,payload:DiscountRewardDraftInput)=>
    writeJson<{mode:"draft_only";reward:DiscountRewardDraft;coupon_created:false}>(
      "PATCH", "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/reward-drafts/"+encodeURIComponent(id)+"/", payload),
  deleteDiscountRewardDraft:(tenantId:string,id:string)=>
    deleteJson<{deleted:true;id:string}>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/reward-drafts/"+encodeURIComponent(id)+"/"),
  setRewardCatalogPublication:(tenantId:string,id:string,published:boolean)=>
    writeJson<{
      reward:DiscountRewardDraft;catalog_published:boolean;
      redemption_enabled:false;coupon_created:false;points_credited:false;points_debited:false
    }>(
      "PATCH","/api/v1/tenants/"+encodeURIComponent(tenantId)+
      "/loyalty/reward-drafts/"+encodeURIComponent(id)+"/publication/",{published}),
  listPointCampaignDrafts:(tenantId:string)=>getJson<{
    mode:"draft_only";activation_available:false;items:PointCampaignDraft[]
  }>("/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/point-campaign-drafts/"),
  savePointCampaignDraft:(tenantId:string,payload:PointCampaignDraftInput)=>
    postJson<{mode:"draft_only";campaign:PointCampaignDraft;messages_sent:false}>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/point-campaign-drafts/",payload),
  updatePointCampaignDraft:(tenantId:string,id:string,payload:PointCampaignDraftInput)=>
    writeJson<{mode:"draft_only";campaign:PointCampaignDraft;messages_sent:false}>(
      "PATCH", "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/point-campaign-drafts/"+encodeURIComponent(id)+"/", payload),
  deletePointCampaignDraft:(tenantId:string,id:string)=>
    deleteJson<{deleted:true;id:string}>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/point-campaign-drafts/"+encodeURIComponent(id)+"/"),
  listManualSales: (tenantId:string)=>getJson<ManualSaleList>(
    "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/sales/manual/"),
  createManualSale: (tenantId:string,data:ManualSaleInput)=>postJson<ManualSaleResult>(
    "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/sales/manual/",data),
  reviewManualSale: (tenantId:string,saleId:string,decision:"approve"|"reject",note:string)=>
    postJson<ManualSaleReviewResult>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/sales/manual/"+
      encodeURIComponent(saleId)+"/review/",{decision,note}),
  getPointRuleDraft: (tenantId:string)=>getJson<{
    mode:"draft_only";activation_available:false;rule:PointRuleDraft|null
  }>("/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/point-rule-draft/"),
  savePointRuleDraft: (tenantId:string,rule:Omit<PointRuleDraft,"version">)=>
    postJson<PointRuleDraftResult>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/loyalty/point-rule-draft/",rule),
  getTenantPrivacyRequests: (tenantId:string) =>
    getJson<PrivacyRequestsSummary>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+"/privacy/requests/"
    ),
  downloadPrivacyReport: async (tenantId:string, requestId:string) => {
    const csrf=cookie("csrftoken");
    if(!csrf)throw new ApiError("Sua sessão expirou. Atualize a página.",403);
    const response=await fetch(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+
      "/privacy/requests/"+encodeURIComponent(requestId)+"/report/",{
        method:"POST",credentials:"same-origin",cache:"no-store",
        headers:{"Content-Type":"application/json","X-CSRFToken":csrf},
        body:"{}",
      }
    );
    if(!response.ok)await readResponse<never>(response);
    return {
      blob:await response.blob(),
      digest:response.headers.get("X-Fideliza-Report-Digest")||"",
      complete:response.headers.get("X-Fideliza-Report-Complete")==="true",
    };
  },
  confirmPrivacyReport: (tenantId:string, requestId:string, digest:string) =>
    postJson<{status:"completed";message:string}>(
      "/api/v1/tenants/"+encodeURIComponent(tenantId)+
      "/privacy/requests/"+encodeURIComponent(requestId)+"/confirm/",
      {confirm:true,digest}
    ),
  getTenantSettings: (tenantId:string) =>
    getJson<TenantPreferences>("/api/v1/tenants/"+encodeURIComponent(tenantId)+"/settings/"),
  saveTenantBranding: (tenantId:string, expectedVersion:number, input:TenantBranding) =>
    writeJson<TenantPreferencesSaved>(
      "PATCH","/api/v1/tenants/"+encodeURIComponent(tenantId)+"/settings/",
      {...input, expected_version:expectedVersion}
    ),
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
  currentProgramTerms: (tenantId: string) =>
    getJson<ProgramTermsStatus>("/api/v1/tenants/" + encodeURIComponent(tenantId) + "/program-terms/"),
  approveProgramTerms: (tenantId: string, input: {version:string;title:string;body:string;privacy_notice:string}) =>
    postJson<ProgramTermsStatus>("/api/v1/tenants/" + encodeURIComponent(tenantId) + "/program-terms/",input),
  createEnrollmentInvitation: (tenantId: string) =>
    postJson<InvitationCreated>("/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/enrollment-invitations/",{}),
  pendingEnrollments: (tenantId: string) =>
    getJson<EnrollmentPendingList>("/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/enrollment-submissions/"),
  previewCustomerMatch: (tenantId:string, submissionId:string) =>
    postJson<CustomerMatchPreview>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/enrollment-submissions/" + encodeURIComponent(submissionId) +
      "/customer-match/preview/", {}
    ),
  approveCustomerLink: (tenantId:string, submissionId:string, customerId:string) =>
    postJson<CustomerLinkApproved>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/enrollment-submissions/" + encodeURIComponent(submissionId) +
      "/customer-match/approve/", {customer_id:customerId, confirm:true}
    ),
  participantWallet: (tenantId: string, participantId: string) =>
    getJson<CashbackWalletView>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/participants/" + encodeURIComponent(participantId) + "/wallet/"
    ),
  recentNuvemshopOrders:(tenantId:string)=>
    getJson<RecentOrdersPreview>("/api/v1/tenants/"+
      encodeURIComponent(tenantId)+"/nuvemshop/orders/recent/preview/"),
  inspectPaidOrder:(tenantId:string,orderId:string)=>
    getJson<PaidOrderInspection>("/api/v1/tenants/"+
      encodeURIComponent(tenantId)+"/nuvemshop/orders/"+
      encodeURIComponent(orderId)+"/preview/"),
  inspectPaidOrderNumber:(tenantId:string,orderNumber:string)=>
    getJson<PaidOrderInspection>("/api/v1/tenants/"+
      encodeURIComponent(tenantId)+"/nuvemshop/orders/by-number/preview/?number="+
      encodeURIComponent(orderNumber)),
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
  login: (email: string, password: string) =>
    postJson<{ authenticated: true; tenants: Store[] }>("/api/v1/auth/login/", { email, password }),
  registerMerchant: (data:{name:string;store_name:string;email:string;password:string}) =>
    postJson<{detail:string}>("/api/v1/auth/register/",data),
  resendMerchantEmail: (email:string) =>
    postJson<{detail:string}>("/api/v1/auth/register/resend/",{email}),
  confirmMerchant: (token:string) =>
    postJson<{authenticated:true;store_linked:true;store_id:string;detail:string}>(
      "/api/v1/auth/register/confirm/",{token}),
  requestMerchantReset: (email:string) =>
    postJson<{detail:string}>("/api/v1/auth/password-reset/request/",{email}),
  confirmMerchantReset: (token:string,password:string) =>
    postJson<{detail:string}>("/api/v1/auth/password-reset/confirm/",{token,password}),
  logout: () => postJson<{ authenticated: false }>("/api/v1/auth/logout/", {}),
  listCampaignDrafts: (tenantId: string) =>
    getJson<CampaignDraftList>("/api/v1/tenants/" + encodeURIComponent(tenantId) + "/campaign-drafts/"),
  createCampaignDraft: (tenantId: string, input: CampaignDraftInput) =>
    postJson<CampaignDraft>("/api/v1/tenants/" + encodeURIComponent(tenantId) + "/campaign-drafts/", input),
  updateCampaignDraft: (tenantId: string, draftId: string, expectedVersion: number, input: CampaignDraftInput) =>
    writeJson<CampaignDraft>("PATCH",
      "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/campaign-drafts/" +
      encodeURIComponent(draftId) + "/", {...input, expected_version: expectedVersion}),
  simulateBenefit: (tenantId: string, draftId: string, input: BenefitScenarioInput) =>
    postJson<BenefitScenarioResult>(
      "/api/v1/tenants/" + encodeURIComponent(tenantId) +
      "/campaign-drafts/" + encodeURIComponent(draftId) + "/simulate/", input
    ),
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

export type MemberClubPublic = {
  store_name:string; store_slug:string;
  branding:{program_name:string;primary_color:string;accent_color:string;support_email:string};
  terms:ProgramTerms|null;
  signup_available:boolean;points_enabled:false;rewards_enabled:false;redemption_enabled:false;
  published_rewards?:MemberClubReward[];
};
export type MemberClubReward = {
  id:string;title:string;points_cost:number;discount_cents:number;
  min_order_cents:number;status:"available"|"locked"|"paused"|"sold_out";
  points_missing:number|null;redemption_enabled:boolean;
};
export type MemberClubPrivate = {
  store_name:string;display_name:string;
  status:"active"|"paused"|"awaiting_link";joined_at:string|null;
  terms:ProgramTerms;
  points_balance:number|null;points_pending:number|null;points_expiring:number|null;
  points_status:"not_active"|"ledger_only"|"verified";
  available_rewards:MemberClubReward[];
  transactions:Array<{id:string;kind:string;points_delta:number;created_at:string;description:string}>;
  redemption_enabled:boolean;orders_verified:boolean;note:string;
};

export type EmailActionResult = {
  status: "email_verified" | "withdrawn";
  identity_verified_in_nuvemshop: boolean;
  participant_created: boolean;
  cashback_enabled: false;
  club_slug?: string | null;
  message: string;
};

export const publicEnrollmentApi = {
  club:(slug:string)=>getJson<MemberClubPublic>("/api/v1/public/clubs/"+encodeURIComponent(slug)+"/"),
  clubMe:(slug:string)=>getJson<MemberClubPrivate>("/api/v1/public/clubs/"+encodeURIComponent(slug)+"/me/"),
  clubRequestAccess:(slug:string,email:string)=>postJson<{status:"accepted"}>(
    "/api/v1/public/clubs/"+encodeURIComponent(slug)+"/access/request/",{email}),
  clubConfirmAccess:(slug:string,token:string)=>postJson<{authenticated:true}>(
    "/api/v1/public/clubs/"+encodeURIComponent(slug)+"/access/confirm/",{token}),
  clubLogout:(slug:string)=>postJson<{authenticated:false}>(
    "/api/v1/public/clubs/"+encodeURIComponent(slug)+"/logout/",{}),
  requestWithdrawal: (slug:string,email:string) =>
    postJson<{status:"accepted";message:string}>(
      "/api/v1/public/programs/"+encodeURIComponent(slug)+"/withdraw-request/",
      {email}
    ),
  confirmEmailAction: (token:string,action:"verify"|"withdraw") =>
    postJson<EmailActionResult>("/api/v1/public/enrollment/email-action/",
      {token,action}),
  store: (slug:string) =>
    getJson<PublicStoreProgram>("/api/v1/public/programs/"+encodeURIComponent(slug)+"/"),
  joinStore: (slug:string,data:{
    name:string;email:string;terms_version:string;
    accepted_terms:boolean;marketing_opt_in:boolean;
  }) => postJson<PublicStoreJoinResult>(
    "/api/v1/public/programs/"+encodeURIComponent(slug)+"/join/",data),
  prepareCsrf: () => merchantApi.getSession(),
  preview: (token:string) =>
    postJson<PublicInvitationPreview>("/api/v1/public/enrollment/preview/",{token}),
  accept: (data:{
    token:string;name:string;email:string;accepted_terms:boolean;marketing_opt_in:boolean;
  }) => postJson<PublicConsentResult>("/api/v1/public/enrollment/accept/",data)
};
