import { useMemo, useState } from "react";
import { AlertTriangle, BadgeCheck, Calculator, Gauge, Info, LockKeyhole, RotateCcw, ShieldAlert } from "lucide-react";
import { brl, parseBrl, parsePercent, simulateMargin, type MarginInput } from "./finance";

type FieldKey =
  | "subtotal" | "discount" | "cogs" | "fee" | "freight" | "other" | "cashback" | "minimum";

type Inputs = Record<FieldKey, string>;

const initial: Inputs = {
  subtotal: "200", discount: "10", cogs: "110",
  fee: "6", freight: "12", other: "4", cashback: "2", minimum: "15"
};
const high: Inputs = { ...initial, cashback: "25" };
const unknown: Inputs = { ...initial, cogs: "" };

const fields: {
  key: FieldKey; label: string; hint: string; suffix: string;
}[] = [
  { key: "subtotal", label: "Subtotal dos produtos", hint: "Antes de cupons e desconto Pix", suffix: "R$" },
  { key: "discount", label: "Descontos existentes", hint: "Cupons, desconto Pix e outras promoções", suffix: "R$" },
  { key: "cogs", label: "Custo da mercadoria", hint: "Deixe vazio quando o custo não estiver confirmado", suffix: "R$" },
  { key: "fee", label: "Taxas do pagamento", hint: "Tarifas e custo da transação", suffix: "R$" },
  { key: "freight", label: "Frete subsidiado", hint: "Valor de frete pago pela loja", suffix: "R$" },
  { key: "other", label: "Outras despesas variáveis", hint: "Impostos, embalagem e outras despesas, se conhecidas", suffix: "R$" },
  { key: "cashback", label: "Cashback proposto", hint: "Crédito futuro sobre a base líquida elegível", suffix: "%" },
  { key: "minimum", label: "Meta mínima de margem", hint: "Margem de contribuição desejada após o benefício", suffix: "%" }
];

function parseValues(values: Inputs): MarginInput {
  const requiredMoney = (s: string) => {
    const parsed = parseBrl(s);
    if (parsed === null) throw new Error("Preencha os valores monetários necessários.");
    return parsed;
  };
  return {
    eligible_subtotal_cents: requiredMoney(values.subtotal),
    existing_discounts_cents: requiredMoney(values.discount),
    cost_of_goods_cents: parseBrl(values.cogs, true),
    payment_fee_cents: requiredMoney(values.fee),
    shipping_subsidy_cents: requiredMoney(values.freight),
    other_variable_costs_cents: requiredMoney(values.other),
    proposed_cashback_bps: parsePercent(values.cashback),
    minimum_margin_bps: parsePercent(values.minimum)
  };
}

function toPercent(bps: number): string {
  return (bps / 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + "%";
}

export default function MarginSimulator() {
  const [values, setValues] = useState<Inputs>(initial);
  const [scenario, setScenario] = useState("base");

  const computation = useMemo(() => {
    try {
      return { result: simulateMargin(parseValues(values)), error: null as string | null };
    } catch (cause) {
      return {
        result: null,
        error: cause instanceof Error ? cause.message : "Revise os valores informados."
      };
    }
  }, [values]);

  const result = computation.result;
  const status = result?.status ?? "invalid";
  const statusInfo = {
    invalid: { title: "Revise os valores", sub: computation.error || "Dados inválidos", tone: "warning" },
    cost_unknown: { title: "Custo desconhecido", sub: "Sem o custo da mercadoria, não recomendamos ativar benefícios.", tone: "warning" },
    margin_already_below_target: { title: "Margem insuficiente", sub: "Esta compra não alcança a margem mínima nem antes do cashback.", tone: "danger" },
    cashback_exceeds_margin: { title: "Cashback acima do limite", sub: "Reduza a taxa ou ajuste os custos para preservar a margem configurada.", tone: "danger" },
    within_target: { title: "Dentro da meta simulada", sub: "O cálculo é favorável, mas ainda exige validação dos custos reais.", tone: "success" }
  }[status];

  const setField = (key: FieldKey, value: string) => {
    setValues(previous => ({ ...previous, [key]: value }));
    setScenario("custom");
  };

  const presets = [
    { id: "base", label: "Margem saudável", data: initial },
    { id: "risk", label: "Cashback arriscado", data: high },
    { id: "unknown", label: "Custo ausente", data: unknown }
  ];

  return <div className="margin-experience">
    <div className="margin-hero">
      <div className="margin-hero-copy">
        <span className="margin-kicker"><Gauge size={16} /> VIDALYS INTELLIGENCE <span>•</span> PRÉVIA</span>
        <h2>Recompensar é fácil.<br/><span>Proteger a margem é inteligência.</span></h2>
        <p>Simule o custo total de uma campanha antes de oferecer cashback. Aqui, a margem é prioridade — não apenas o desconto.</p>
        <span className="margin-disclaimer"><LockKeyhole size={15}/> Cálculos locais com dados digitados. Nenhuma campanha é ativada.</span>
      </div>
      <div className="margin-hero-symbol" aria-hidden="true"><Calculator size={68} strokeWidth={1.3}/></div>
    </div>

    <div className="margin-heading">
      <div><span className="panel-kicker">CENTRAL DE DECISÃO</span><h2>Simulador de rentabilidade</h2><p>Compare cenários e descubra quando uma recompensa pode comprometer o pedido.</p></div>
      <button className="margin-reset" onClick={() => { setValues(initial); setScenario("base"); }}><RotateCcw size={16}/> Restaurar</button>
    </div>

    <div className="margin-presets" aria-label="Cenários de simulação">
      {presets.map(p => <button key={p.id} className={"margin-preset" + (scenario === p.id ? " active" : "")}
        aria-pressed={scenario === p.id} onClick={() => { setValues(p.data); setScenario(p.id); }}>{p.label}</button>)}
    </div>

    <div className="margin-layout">
      <section className="margin-panel margin-form">
        <header className="margin-panel-head">
          <span className="margin-heading-icon"><Calculator size={20}/></span>
          <div><h3>Dados da venda</h3><p>Preencha valores reais quando estiverem disponíveis.</p></div>
        </header>
        <div className="margin-fields">
          {fields.map(f => <label className="margin-field" key={f.key}>
            <span className="margin-field-label">{f.label}</span>
            <span className="margin-field-input">
              <span>{f.suffix}</span>
              <input type="text" inputMode="decimal" value={values[f.key]}
                onChange={event => setField(f.key, event.target.value)}
                placeholder={f.key === "cogs" ? "Não informado" : "0,00"}
                aria-label={f.label} />
            </span>
            <small>{f.hint}</small>
          </label>)}
        </div>
      </section>

      <section className="margin-panel margin-results" aria-live="polite">
        <header className="margin-panel-head">
          <span className="margin-heading-icon blue"><Gauge size={21}/></span>
          <div><h3>Diagnóstico da campanha</h3><p>Exposição potencial, custos e margem estimada.</p></div>
        </header>

        <div className={"margin-status " + statusInfo.tone}>
          {statusInfo.tone === "success" ? <BadgeCheck size={21}/> : <ShieldAlert size={21}/>}
          <div><b>{statusInfo.title}</b><p>{statusInfo.sub}</p></div>
        </div>

        <div className="margin-result-grid">
          <div className="margin-result-main"><span>Cashback potencial</span><strong>{result ? brl(result.estimated_cashback_exposure_cents) : "—"}</strong><small>Crédito promocional futuro, não valor resgatado</small></div>
          <div className="margin-result-light"><span>Receita elegível líquida</span><strong>{result ? brl(result.eligible_net_revenue_cents) : "—"}</strong></div>
          <div className="margin-result-light"><span>Contribuição após incentivo</span><strong>{result?.contribution_after_cents !== null && result?.contribution_after_cents !== undefined ? brl(result.contribution_after_cents) : "Desconhecida"}</strong></div>
        </div>

        <div className="margin-threshold">
          <div className="margin-threshold-head"><span>Margem após recompensa</span><b>{result?.margin_after_bps !== null && result?.margin_after_bps !== undefined ? toPercent(result.margin_after_bps) : "—"}</b></div>
          <div className="margin-meter" aria-hidden="true"><span style={{ width: result?.margin_after_bps === null || result?.margin_after_bps === undefined ? "0%" : Math.min(100, Math.max(0, result.margin_after_bps / 100)) + "%" }} className={statusInfo.tone}/></div>
          <p>Meta mínima configurada: <b>{result ? toPercent(result.minimum_margin_bps) : "—"}</b></p>
        </div>

        <div className="margin-safe-row"><span>Maior taxa estimada que preserva a meta</span><strong>{result?.maximum_safe_cashback_bps !== null && result?.maximum_safe_cashback_bps !== undefined ? toPercent(result.maximum_safe_cashback_bps) : "Indisponível"}</strong></div>
        <div className="margin-safe-row"><span>Orçamento máximo para recompensa nesta venda</span><strong>{result?.safe_cashback_budget_cents !== null && result?.safe_cashback_budget_cents !== undefined ? brl(result.safe_cashback_budget_cents) : "Indisponível"}</strong></div>

        <div className="margin-note"><Info size={19}/><p><b>Sem promessa de lucro.</b> O cálculo não conhece custos não informados e não considera impacto na recompra, impostos adicionais ou resgate efetivo. É uma análise preliminar, não uma autorização para ativar promoção.</p></div>
      </section>
    </div>

    <div className="margin-next"><AlertTriangle size={18}/><span>Próximo diferencial planejado: simular também a <b>recompra incremental</b> e o orçamento mensal da campanha, somente após termos dados confiáveis e grupos comparáveis.</span></div>
  </div>;
}
