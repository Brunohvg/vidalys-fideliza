import {BadgeCheck, Check, Gauge, Info, ShieldAlert, BarChart3, X} from "lucide-react";
import {brl, percent, points, ratio} from "./format";
import type {LiftResult, MerchantInsights, RateResult} from "./types";
import "./differentials.css";

/* Painel do lojista — inteligência do programa. Sem métrica sem fonte. */

export function ClaritySeal({data}: {data: MerchantInsights}) {
  const {seal, items, summary} = data.clarity;
  return <section className="vfd-card vfd-panel" aria-labelledby="vfd-seal-title">
    <header className="vfd-panel-head">
      <span className={"vfd-icon-bubble " + (seal ? "vfd-icon-ok" : "vfd-icon-warn")} aria-hidden="true">
        {seal ? <BadgeCheck size={22}/> : <ShieldAlert size={22}/>}
      </span>
      <div>
        <span className="vfd-kicker">Selo Clube Claro</span>
        <h2 id="vfd-seal-title">{seal ? "Seu regulamento é claro para o cliente" : "Faltam ajustes para o selo"}</h2>
      </div>
    </header>
    <ul className="vfd-checklist">
      {items.map(item => <li key={item.key} data-ok={item.ok}>
        <span className="vfd-check-icon" aria-hidden="true">{item.ok ? <Check size={15}/> : <X size={15}/>}</span>
        <div>
          <strong>{item.label}{!item.required && <em> · recomendação</em>}</strong>
          {item.detail && <span>{item.detail}</span>}
        </div>
        <span className="vfd-sr">{item.ok ? "aprovado" : "pendente"}</span>
      </li>)}
    </ul>
    <div className="vfd-preview">
      <span className="vfd-kicker">Como o cliente lê sua regra</span>
      <p><strong>{summary.headline}</strong></p>
      <ul>{summary.sentences.slice(1).map(sentence => <li key={sentence}>{sentence}</li>)}</ul>
    </div>
  </section>;
}

export function MarginRanking({data}: {data: MerchantInsights}) {
  const {ranked, excluded} = data.margin;
  const best = ranked.length ? Math.max(...ranked.map(item => item.value_ratio)) : 0;
  return <section className="vfd-card vfd-panel" aria-labelledby="vfd-margin-title">
    <header className="vfd-panel-head">
      <span className="vfd-icon-bubble vfd-icon-reward" aria-hidden="true"><Gauge size={22}/></span>
      <div>
        <span className="vfd-kicker">Meta com Margem</span>
        <h2 id="vfd-margin-title">Recompensas que o cliente valoriza e custam pouco</h2>
      </div>
    </header>
    <p className="vfd-panel-lead">O clube sugere ao cliente, como próxima meta, a recompensa
      próxima do saldo dele que entrega mais valor por real de custo seu.</p>
    {ranked.length === 0 ? <p className="vfd-empty">Informe o custo das recompensas para ver o ranking.</p> :
      <div className="vfd-table-wrap"><table className="vfd-table">
        <thead><tr><th scope="col">Recompensa</th><th scope="col">Pontos</th>
          <th scope="col">Vale para o cliente</th><th scope="col">Seu custo</th>
          <th scope="col">Valor por R$ 1 de custo</th></tr></thead>
        <tbody>{ranked.map(item => <tr key={item.id}>
          <th scope="row">{item.title}</th>
          <td>{points(item.points_cost, true)}</td>
          <td>{brl(item.perceived_value_cents)}</td>
          <td>{brl(item.merchant_cost_cents)}</td>
          <td><div className="vfd-ratio"><span style={{width: Math.round(item.value_ratio / best * 100) + "%"}}/>
            <b>{ratio(item.value_ratio)}</b></div></td>
        </tr>)}</tbody>
      </table></div>}
    {excluded.length > 0 && <ul className="vfd-excluded" aria-label="Fora do ranking">
      {excluded.map(item => <li key={item.id}><Info size={14} aria-hidden="true"/>
        <strong>{item.title}</strong> — {item.reason_label}</li>)}
    </ul>}
  </section>;
}

function rateText(result: RateResult | null) {
  if (!result) return {value: "Sem dados", note: "Disponível após as primeiras vendas conferidas."};
  if (result.status !== "ok" || result.value === null || result.low === null || result.high === null)
    return {value: "Dados insuficientes", note: `${result.total} clientes no período; mínimo de 30 para calcular.`};
  return {value: percent(result.value),
    note: `Entre ${percent(result.low)} e ${percent(result.high)} (95% de confiança, ${result.total} clientes).`};
}

function liftText(result: LiftResult | null) {
  const labels: Record<LiftResult["status"], string> = {
    dados_insuficientes: "Dados insuficientes",
    inconclusivo: "Ainda inconclusivo",
    positivo: "Efeito positivo comprovado",
    negativo: "Efeito negativo",
  };
  if (!result) return {value: "Sem grupo de controle", note: "Ative o grupo de controle de mensagens para medir efeito."};
  if (result.status === "dados_insuficientes" || result.difference === null)
    return {value: labels[result.status], note: "Cada grupo precisa de pelo menos 100 clientes. Não afirmamos aumento sem prova."};
  return {value: labels[result.status],
    note: `Diferença de ${percent(result.difference)} (entre ${percent(result.low ?? 0)} e ${percent(result.high ?? 0)}).`};
}

export function ClubHealth({data}: {data: MerchantInsights}) {
  const {liability, expiring_30d_points, repurchase_90d, lift} = data.health;
  const liabilityValue = !liability ? "Sem dados"
    : liability.basis === "custo_desconhecido" ? "Custo desconhecido"
    : liability.basis === "sem_pontos" ? brl(0)
    : `${brl(liability.low_cents ?? 0)} a ${brl(liability.high_cents ?? 0)}`;
  const repurchase = rateText(repurchase_90d);
  const effect = liftText(lift);
  const tiles = [
    {label: "Custo potencial dos pontos em aberto", value: liabilityValue,
      note: "Faixa entre a recompensa mais barata e a mais cara por ponto."},
    {label: "Pontos que vencem em 30 dias", value: expiring_30d_points === null ? "Sem dados" : points(expiring_30d_points, true),
      note: "Os clientes recebem um aviso consolidado antes do vencimento."},
    {label: "Recompra em 90 dias", ...repurchase},
    {label: "Efeito do clube vs. controle", ...effect},
  ];
  return <section className="vfd-card vfd-panel" aria-labelledby="vfd-health-title">
    <header className="vfd-panel-head">
      <span className="vfd-icon-bubble vfd-icon-brand" aria-hidden="true"><BarChart3 size={22}/></span>
      <div>
        <span className="vfd-kicker">Saúde do clube</span>
        <h2 id="vfd-health-title">Retorno com prova, não com promessa</h2>
      </div>
    </header>
    <div className="vfd-tiles">
      {tiles.map(tile => <article key={tile.label} className="vfd-tile">
        <span>{tile.label}</span><strong>{tile.value}</strong><small>{tile.note}</small>
      </article>)}
    </div>
  </section>;
}

export function ProgramInsights({data}: {data: MerchantInsights}) {
  return <div className="vfd-insights">
    <ClubHealth data={data}/>
    <div className="vfd-insights-grid">
      <ClaritySeal data={data}/>
      <MarginRanking data={data}/>
    </div>
  </div>;
}
