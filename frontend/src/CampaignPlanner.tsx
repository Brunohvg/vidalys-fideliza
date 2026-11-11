import { useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowRight, BadgeCheck, Calculator, ChevronDown,
  CircleDollarSign, Coins, Gauge, Info, LockKeyhole, RotateCcw,
  ShieldAlert, Target, TrendingUp
} from "lucide-react";
import {
  ApiError, merchantApi, type CampaignPlanInput, type CampaignPlanResult
} from "./api";
import { brl, parseBrl, parsePercent } from "./finance";

type Field = "subtotal" | "discount" | "cogs" | "payment" | "shipping" |
  "other" | "cashback" | "minimum" | "orders" | "budget" | "committed";

type Values = Record<Field, string>;

const defaultValues: Values = {
  subtotal: "200", discount: "10", cogs: "110", payment: "6",
  shipping: "12", other: "4", cashback: "2", minimum: "15",
  orders: "100", budget: "200", committed: "20"
};

const presets = [
  { id: "budget", name: "Orçamento apertado", values: defaultValues },
  { id: "safe", name: "Ajustar orçamento", values: { ...defaultValues, budget: "600" } },
  { id: "unknown", name: "Sem custo validado", values: { ...defaultValues, cogs: "" } }
];

const fields: {
  key: Field; title: string; tip: string; unit: string; required: boolean
}[] = [
  { key: "subtotal", title: "Ticket elegível por pedido", tip: "Produtos antes dos descontos.", unit: "R$", required: true },
  { key: "discount", title: "Desconto por pedido", tip: "Inclua Pix e cupons.", unit: "R$", required: true },
  { key: "cogs", title: "Custo da mercadoria", tip: "Vazio = custo desconhecido.", unit: "R$", required: false },
  { key: "payment", title: "Taxas do pagamento", tip: "Taxas assumidas pela loja.", unit: "R$", required: true },
  { key: "shipping", title: "Frete subsidiado", tip: "O custo da loja, não o frete pago pelo cliente.", unit: "R$", required: true },
  { key: "other", title: "Outros custos variáveis", tip: "Inclua impostos e embalagem, quando conhecidos.", unit: "R$", required: true },
];

function parseInputs(values: Values): CampaignPlanInput {
  const amount = (field: Field, nullable = false) => {
    const cents = parseBrl(values[field], nullable);
    if (cents === null && !nullable) throw new Error("Preencha os valores obrigatórios.");
    return cents;
  };
  if (!/^\d+$/.test(values.orders.trim())) {
    throw new Error("Informe uma quantidade inteira de pedidos.");
  }
  const orders = Number(values.orders);
  if (!Number.isSafeInteger(orders) || orders < 1 || orders > 50000) {
    throw new Error("A quantidade precisa estar entre 1 e 50.000 pedidos.");
  }
  return {
    eligible_subtotal_cents: amount("subtotal") as number,
    existing_discounts_cents: amount("discount") as number,
    cost_of_goods_cents: amount("cogs", true),
    payment_fee_cents: amount("payment") as number,
    shipping_subsidy_cents: amount("shipping") as number,
    other_variable_costs_cents: amount("other") as number,
    proposed_cashback_bps: parsePercent(values.cashback),
    minimum_margin_bps: parsePercent(values.minimum),
    projected_paid_orders: orders,
    campaign_budget_cents: amount("budget") as number,
    already_committed_cents: amount("committed") as number
  };
}

function percent(value: number) {
  return (value / 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + "%";
}

const statusInfo: Record<CampaignPlanResult["status"], {title: string; text: string; tone: string}> = {
  within_limits: {
    title: "Dentro dos limites simulados",
    text: "O cenário cabe no orçamento e preserva a margem mínima informada. Não é autorização automática.",
    tone: "success"
  },
  campaign_budget_exceeded: {
    title: "O orçamento não comporta o volume",
    text: "Para esse número de compras, a exposição ao cashback pode superar o limite disponível.",
    tone: "warning"
  },
  cashback_exceeds_margin: {
    title: "O cashback compromete a margem",
    text: "Mesmo com orçamento disponível, essa taxa ultrapassa a margem mínima definida.",
    tone: "danger"
  },
  margin_already_below_target: {
    title: "Margem já abaixo da meta",
    text: "Antes de oferecer crédito, revise os custos e a margem de contribuição da venda.",
    tone: "danger"
  },
  cost_unknown: {
    title: "Custo não informado",
    text: "Sem custo da mercadoria confirmado, não existe um teto de cashback seguro.",
    tone: "warning"
  },
  budget_already_exceeded: {
    title: "Orçamento já comprometido",
    text: "Os compromissos informados são maiores que o limite mensal configurado.",
    tone: "danger"
  }
};

export default function CampaignPlanner({ tenantId }: { tenantId: string }) {
  const [values, setValues] = useState<Values>(defaultValues);
  const [preset, setPreset] = useState("budget");
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CampaignPlanResult | null>(null);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);

  const validation = useMemo(() => {
    try {
      return { data: parseInputs(values), error: "" };
    } catch (cause) {
      return { data: null, error: cause instanceof Error ? cause.message : "Valores inválidos." };
    }
  }, [values]);

  const change = (field: Field, value: string) => {
    requestVersion.current++;
    setValues(old => ({ ...old, [field]: value }));
    setPreset("custom");
    setBusy(false); setResult(null); setError("");
  };

  const selectPreset = (id: string, selected: Values) => {
    requestVersion.current++;
    setValues(selected); setPreset(id); setResult(null); setBusy(false); setError("");
  };

  const calculate = async () => {
    if (!validation.data) { setError(validation.error); return; }
    setError(""); setResult(null); setBusy(true);
    const version = ++requestVersion.current;
    try {
      const response = await merchantApi.previewCampaign(tenantId, validation.data);
      if (version === requestVersion.current) setResult(response);
    } catch (cause) {
      if (version === requestVersion.current) setError(
        cause instanceof ApiError ? cause.message : "Não foi possível acessar o servidor."
      );
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };

  const info = result ? statusInfo[result.status] : null;
  const share = result && result.campaign_budget_cents > 0
    ? Math.round(result.projected_total_exposure_cents / result.campaign_budget_cents * 100)
    : (result?.projected_total_exposure_cents ? 100 : 0);

  return <div className="campaign-workspace">
    <section className="campaign-hero">
      <div>
        <div className="campaign-eyebrow"><Target size={16}/> CONTROLE DE CAMPANHAS <span>•</span> LABORATÓRIO</div>
        <h2>Mais recompra.<br/><em>Menos desconto no escuro.</em></h2>
        <p>Planeje quanto sua campanha poderá distribuir em benefícios e descubra o risco antes de colocá-la no ar.</p>
        <div className="campaign-hero-meta"><LockKeyhole size={15}/> Simulação privada. Nenhuma campanha é criada.</div>
      </div>
      <span className="campaign-hero-icon"><Coins size={65} strokeWidth={1.4}/></span>
    </section>

    <div className="campaign-heading">
      <div><span className="portal-eyebrow">SIMULADOR DE ORÇAMENTO</span><h2>Seu plano de fidelidade</h2><p>Trabalhe com hipóteses; os números não vêm das vendas da loja.</p></div>
      <button className="campaign-reset" onClick={() => selectPreset("budget", defaultValues)}>
        <RotateCcw size={16}/> Restaurar
      </button>
    </div>
    <div className="campaign-presets" aria-label="Cenários para explorar">
      {presets.map(p => <button key={p.id} aria-pressed={preset === p.id}
        className={"campaign-preset" + (preset === p.id ? " current" : "")}
        onClick={() => selectPreset(p.id, p.values)}>{p.name}</button>)}
    </div>
    <div className="campaign-explanation"><Info size={18}/><div><strong>Comece pelos seus números.</strong> Os campos estão preenchidos com exemplos. Informe seu ticket médio, custos e expectativa de pedidos pagos para testar a campanha.</div></div>

    <div className="campaign-grid">
      <section className="campaign-card campaign-editor">
        <div className="campaign-card-header"><span className="campaign-card-symbol"><Calculator size={20}/></span>
          <div><h3>Configure o cenário</h3><p>Quatro decisões principais, com custos extras opcionais.</p></div></div>

        <div className="campaign-main-fields">
          <label className="campaign-field"><span>Pedidos pagos previstos <small>Hipótese mensal</small></span>
            <div className="campaign-input"><span><TrendingUp size={16}/></span><input inputMode="numeric" type="text" aria-label="Pedidos pagos previstos" value={values.orders} onChange={e=>change("orders",e.target.value)}/></div></label>
          <label className="campaign-field"><span>Orçamento total <small>Limite mensal de créditos</small></span>
            <div className="campaign-input"><span>R$</span><input inputMode="decimal" type="text" aria-label="Orçamento total" value={values.budget} onChange={e=>change("budget",e.target.value)}/></div></label>
          <label className="campaign-field"><span>Cashback proposto <small>Percentual do pedido elegível</small></span>
            <div className="campaign-input"><span>%</span><input inputMode="decimal" type="text" aria-label="Cashback proposto" value={values.cashback} onChange={e=>change("cashback",e.target.value)}/></div></label>
          <label className="campaign-field"><span>Margem mínima <small>Quanto deseja preservar</small></span>
            <div className="campaign-input"><span>%</span><input inputMode="decimal" type="text" aria-label="Margem mínima" value={values.minimum} onChange={e=>change("minimum",e.target.value)}/></div></label>
        </div>
        <button className="campaign-expand" aria-expanded={advanced} onClick={()=>setAdvanced(v=>!v)}>
          <span><Gauge size={17}/> {advanced ? "Ocultar valores de custo" : "Revisar os custos por pedido"}</span>
          <ChevronDown size={17} className={advanced ? "rotated" : ""}/>
        </button>
        {advanced && <div className="campaign-cost-fields">
          {fields.map(field => <label className="campaign-field" key={field.key}>
            <span>{field.title}<small>{field.tip}</small></span>
            <div className="campaign-input"><span>{field.unit}</span><input type="text" inputMode="decimal"
              aria-label={field.title} value={values[field.key]}
              placeholder={field.required ? "0,00" : "Não informado"}
              onChange={e=>change(field.key,e.target.value)}/></div>
          </label>)}
          <label className="campaign-field"><span>Créditos já comprometidos <small>Saldo informado manualmente</small></span>
            <div className="campaign-input"><span>R$</span><input type="text" inputMode="decimal"
              aria-label="Créditos já comprometidos" value={values.committed}
              onChange={e=>change("committed",e.target.value)}/></div></label>
        </div>}
        {validation.error && <div className="campaign-error" role="alert">{validation.error}</div>}
        {error && <div className="campaign-error" role="alert">{error}</div>}
        <button className="portal-primary campaign-action" type="button" disabled={busy || Boolean(validation.error)} onClick={calculate}>
          {busy ? "Calculando o cenário…" : "Analisar orçamento e margem"} <ArrowRight size={18}/>
        </button>
        <div className="campaign-safety"><LockKeyhole size={15}/> Cálculo no servidor. Sem alterações na carteira, Nuvemshop ou campanhas.</div>
      </section>
      <section className="campaign-card campaign-outcomes" aria-live="polite">
        <div className="campaign-card-header"><span className="campaign-card-symbol aqua"><CircleDollarSign size={22}/></span>
          <div><h3>Resultado do planejamento</h3><p>Exposição máxima ao crédito promocional.</p></div></div>

        {!result ? <div className="campaign-pending"><Target size={36}/>
          <h3>{busy ? "Analisando seu cenário…" : "Pronto para simular"}</h3>
          <p>Preencha os campos e clique em <b>Analisar orçamento e margem</b>. Nenhuma campanha será ativada.</p>
        </div> : <>
          <div className={"campaign-verdict " + info?.tone}>
            {info?.tone === "success" ? <BadgeCheck size={22}/> : <ShieldAlert size={22}/>}
            <div><b>{info?.title}</b><p>{info?.text}</p></div>
          </div>
          <div className="campaign-result-hero"><span>Exposição total projetada</span>
            <strong>{brl(result.projected_total_exposure_cents)}</strong>
            <small>Inclui o compromisso prévio digitado e o crédito potencial novo.</small>
          </div>
          <div className="campaign-meter-head"><span>Utilização hipotética do orçamento</span><b>{share}%</b></div>
          <div className="campaign-meter" role="progressbar" aria-label="Uso do orçamento" aria-valuenow={Math.min(100,share)} aria-valuemin={0} aria-valuemax={100}>
            <span style={{width: Math.min(100,share) + "%"}} className={share>100?"danger":"safe"}/></div>
          <div className="campaign-result-grid">
            <div><span>Orçamento informado</span><b>{brl(result.campaign_budget_cents)}</b></div>
            <div><span>Disponível antes da campanha</span><b>{brl(result.available_campaign_budget_cents)}</b></div>
            <div><span>Crédito por pedido</span><b>{brl(result.per_order_cashback_cents)}</b></div>
            <div><span>Pedidos que cabem no saldo*</span><b>{result.estimated_order_capacity===null?"Sem limite por crédito":result.estimated_order_capacity.toLocaleString("pt-BR")}</b></div>
          </div>
          <div className="campaign-recommendation">
            <span><Gauge size={18}/> Maior taxa que respeita os limites informados</span>
            <strong>{result.suggested_limit_rate_bps===null?"Não calculável":percent(result.suggested_limit_rate_bps)}</strong>
            <small>É um teto matemático, não uma recomendação comercial. Custos omitidos podem tornar esse percentual inviável.</small>
          </div>
          <div className="campaign-footnote"><AlertTriangle size={17}/>
            <p>* O número de pedidos considera apenas o orçamento destinado ao crédito proposto. Não representa previsão de vendas nem validação fiscal.</p>
          </div>
        </>}
      </section>
    </div>
    <div className="campaign-next"><Info size={18}/> A próxima evolução conecta o custo real por SKU e permite montar campanhas com limites de resgate e exclusões, após validação da Nuvemshop.</div>
  </div>;
}
