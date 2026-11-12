import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, CheckCircle2, Info, LockKeyhole, ShieldAlert, Sparkles } from "lucide-react";
import { ApiError, merchantApi, type BenefitScenarioResult, type CampaignDraft } from "./api";
import { brl } from "./finance";

const descriptions: Record<BenefitScenarioResult["state"], string> = {
  hypothetical_match: "Este cliente fictício se enquadraria na meta. O crédito depende de compras e pagamentos realmente verificados.",
  goal_not_met: "Neste cenário, a pessoa ainda não atingiu o objetivo da campanha.",
  budget_insufficient: "A recompensa prevista ultrapassaria o orçamento hipoteticamente disponível.",
  reward_below_one_cent: "O valor dessa compra geraria menos de um centavo de benefício."
};

export default function BenefitScenario({
  tenantId, draft, orderAmountCents
}: {
  tenantId: string; draft: CampaignDraft; orderAmountCents: number
}) {
  const [priorOrders, setPriorOrders] = useState(
    draft.goal === "recurrence" ? "2" : "1"
  );
  const [daysInactive, setDaysInactive] = useState("60");
  const [result, setResult] = useState<BenefitScenarioResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);

  useEffect(() => {
    requestVersion.current++;
    setResult(null);
    setError("");
    setPriorOrders(draft.goal === "recurrence" ? "2" : "1");
    setDaysInactive("60");
    setBusy(false);
  }, [tenantId, draft.id, draft.version, draft.goal, orderAmountCents]);

  useEffect(() => () => { requestVersion.current++; }, []);

  const updatePrior = (value: string) => {
    requestVersion.current++;
    setPriorOrders(value);
    setResult(null);
    setError("");
    setBusy(false);
  };
  const updateDays = (value: string) => {
    requestVersion.current++;
    setDaysInactive(value);
    setResult(null);
    setError("");
    setBusy(false);
  };

  const simulate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!/^\d{1,5}$/.test(priorOrders.trim()) || Number(priorOrders) > 50000) {
      setError("Escolha uma quantidade válida de compras anteriores.");
      return;
    }
    const previous = Number(priorOrders);
    if (draft.goal === "reactivation" &&
        (previous === 0 || !/^\d{1,5}$/.test(daysInactive.trim()) ||
         Number(daysInactive) > 36500)) {
      setError("Informe pelo menos uma compra anterior e dias de inatividade válidos.");
      return;
    }
    setError("");
    setResult(null);
    setBusy(true);
    const version = ++requestVersion.current;
    try {
      const response = await merchantApi.simulateBenefit(tenantId, draft.id, {
        order_amount_cents: orderAmountCents,
        prior_paid_orders: previous,
        ...(draft.goal === "reactivation" ?
          { days_since_last_paid_order: Number(daysInactive) } : {}),
        committed_budget_cents: 0
      });
      if (version === requestVersion.current) setResult(response);
    } catch (cause) {
      if (version === requestVersion.current) {
        setError(cause instanceof ApiError ? cause.message : "Falha ao calcular este cenário.");
      }
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };

  return <section className="xp-benefit-scenario" aria-label="Motor de benefícios em teste">
    <div className="xp-benefit-scenario-head">
      <span className="xp-benefit-mark"><Sparkles size={20} /></span>
      <div><span className="portal-eyebrow">MOTOR DE BENEFÍCIOS · SIMULAÇÃO</span>
        <h3>Quem receberia este benefício?</h3>
        <p>Teste a regra salva com uma compra fictícia, sem consultar clientes reais.</p>
      </div>
    </div>
    <form onSubmit={simulate}>
      <div className="xp-benefit-scenario-fields">
        <label>Compras anteriores da pessoa
          <select value={priorOrders} onChange={e => updatePrior(e.target.value)}>
            <option value="0">Nenhuma compra anterior</option>
            <option value="1">1 compra anterior</option>
            <option value="2">2 compras anteriores</option>
            <option value="3">3 compras anteriores</option>
            <option value="6">6 compras anteriores</option>
          </select>
        </label>
        {draft.goal === "reactivation" && <label>Dias desde a última compra
          <input inputMode="numeric" value={daysInactive}
            onChange={e => updateDays(e.target.value)} aria-label="Dias sem comprar"/>
        </label>}
        <div className="xp-benefit-fixed">
          <span>Valor hipotético da compra</span><strong>{brl(orderAmountCents)}</strong>
          <small>Usa o ticket configurado neste rascunho.</small>
        </div>
      </div>
      {error && <p role="alert" className="xp-draft-error">{error}</p>}
      <button type="submit" disabled={busy} className="xp-draft-new xp-benefit-try">
        {busy ? "Calculando…" : "Testar esta regra"} <ArrowRight size={16}/>
      </button>
    </form>
    {result && <div className="xp-benefit-scenario-result" role="status" aria-live="polite">
      <span className="xp-benefit-result-icon">
        {result.state === "hypothetical_match" ? <CheckCircle2 size={19}/> : <ShieldAlert size={19}/>}
      </span>
      <div><strong>{result.state === "hypothetical_match"
        ? "Cumpriria a regra simulada" : "Benefício não seria concedido neste cenário"}</strong>
        <p>{descriptions[result.state]}</p>
        <div className="xp-benefit-numbers">
          <span>Recompensa simulada <b>{brl(result.estimated_reward_cents)}</b></span>
          <span>Orçamento hipotético restante <b>{brl(result.remaining_budget_cents)}</b></span>
        </div>
      </div>
    </div>}
    <p className="xp-benefit-warning"><LockKeyhole size={15}/>
      Não concede pontos, cashback ou cupons. O cenário assume orçamento integralmente disponível;
      pagamentos, custo e margem ainda precisam ser confirmados.
    </p>
    <p className="xp-benefit-note"><Info size={14}/>
      A próxima etapa integra compras comprovadas e protege saldos contra estornos.
    </p>
  </section>;
}
