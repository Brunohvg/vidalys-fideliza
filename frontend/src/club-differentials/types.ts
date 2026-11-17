/* Contrato gerado por backend/apps/loyalty/engine/payloads.py.
   Os fixtures em ./fixtures são produzidos a partir do motor Python. */

export type RuleSummary = { headline: string; sentences: string[] };

export type ClubGoal = {
  reward_id: string;
  title: string;
  points_cost: number;
  missing_points: number;
  missing_spend_cents: number;
  progress_percent: number;
  message: string;
  redeemable_now: string[];
};

export type ClubRewardState = "resgatavel" | "faltam" | "indisponivel" | "em_preparacao";

export type ClubReward = {
  id: string;
  title: string;
  points_cost: number;
  perceived_value_cents: number;
  state: ClubRewardState;
  missing_points: number | null;
};

export type ClubInsights = {
  ledger_active: boolean;
  store: { name: string; club_url: string };
  rule: RuleSummary;
  balance: { available: number; pending: number } | null;
  expiring: { points: number; earliest_expiry: string; days_left: number } | null;
  goal: ClubGoal | null;
  rewards: ClubReward[];
  milestones: { key: string; title: string; message: string }[];
};

export type ClarityItem = {
  key: string;
  label: string;
  ok: boolean;
  required: boolean;
  detail: string;
};

export type RateResult = {
  status: "ok" | "dados_insuficientes";
  value: number | null;
  low: number | null;
  high: number | null;
  successes: number;
  total: number;
};

export type LiftResult = {
  status: "dados_insuficientes" | "inconclusivo" | "positivo" | "negativo";
  difference: number | null;
  low: number | null;
  high: number | null;
};

export type MerchantInsights = {
  clarity: { seal: boolean; items: ClarityItem[]; summary: RuleSummary };
  margin: {
    ranked: {
      id: string;
      title: string;
      points_cost: number;
      perceived_value_cents: number;
      merchant_cost_cents: number;
      value_ratio: number;
    }[];
    excluded: { id: string; title: string; reason: string; reason_label: string }[];
  };
  health: {
    liability: { low_cents: number | null; high_cents: number | null; basis: string } | null;
    expiring_30d_points: number | null;
    repurchase_90d: RateResult | null;
    lift: LiftResult | null;
  };
};
