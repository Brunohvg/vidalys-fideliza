import {useEffect,useState} from "react";
import {AlertTriangle,CircleDollarSign,Clock3,Percent} from "lucide-react";
import {merchantApi,type Store} from "./api";
import {percentText,pointValueText,summarizeClub,type ClubSummary} from "./club-summary";

/* Topo do Clube: a regra e as recompensas viram uma frase e três números.
   Dado indisponível não vira zero; o cartão some se não houver permissão. */
export default function ClubSummaryCard({tenantId,role,refreshKey}:{
  tenantId:string;role:Store["role"];refreshKey:string;
}){
  const canManage=role==="owner"||role==="admin";
  const [summary,setSummary]=useState<ClubSummary|null>(null);
  const [holdDays,setHoldDays]=useState<number|null>(null);
  const [failed,setFailed]=useState(false);
  useEffect(()=>{
    if(!canManage)return;
    let active=true;setFailed(false);
    Promise.all([merchantApi.getPointRuleDraft(tenantId),merchantApi.listDiscountRewardDrafts(tenantId)])
      .then(([rule,rewards])=>{
        if(!active)return;
        setHoldDays(rule.rule?rule.rule.hold_days:null);
        setSummary(summarizeClub(rule.rule,rewards.items));
      }).catch(()=>{if(active){setSummary(null);setFailed(true);}});
    return()=>{active=false};
  },[tenantId,canManage,refreshKey]);
  if(!canManage)return null;
  if(failed)return <p className="vf-club-summary-error" role="status">Não foi possível montar o resumo do clube agora.</p>;
  if(!summary)return <section className="vf-club-summary" aria-busy="true" aria-label="Resumo do clube"><p>Montando o resumo do clube…</p></section>;
  const ret=summary.returnBps;
  const value=summary.pointValue;
  return <section className="vf-club-summary" aria-labelledby="vf-club-summary-title">
    <header>
      <span className={"vf-club-stage"+(summary.stage==="ready"?" is-ready":"")}>
        {summary.stage==="ready"?"Pronto para testar":"Em montagem"}</span>
      <h2 id="vf-club-summary-title">Seu clube em uma frase</h2>
    </header>
    {summary.sentences.length>0
      ?<p className="vf-club-sentence">{summary.sentences.join(" ")}</p>
      :<p className="vf-club-sentence">Defina a regra de pontos e a primeira recompensa para ver o resumo.</p>}
    <dl className="vf-club-facts">
      <div><dt><Percent size={16}/> Cliente recebe de volta</dt>
        <dd>{ret?ret.min===ret.max?percentText(ret.max):`${percentText(ret.min)} a ${percentText(ret.max)}`:"—"}</dd></div>
      <div><dt><CircleDollarSign size={16}/> 1 ponto vale</dt>
        <dd>{value?value.min===value.max?pointValueText(value.max):`${pointValueText(value.min)} a ${pointValueText(value.max)}`:"—"}</dd></div>
      <div><dt><Clock3 size={16}/> Pontos liberados em</dt>
        <dd>{holdDays===null?"—":holdDays===0?"na hora":`${holdDays} dia${holdDays===1?"":"s"}`}</dd></div>
    </dl>
    {summary.warnings.length>0&&<ul className="vf-club-warnings" aria-label="Pontos de atenção do clube">
      {summary.warnings.map(item=><li key={item.key}><AlertTriangle size={16}/><span>{item.text}</span></li>)}
    </ul>}
  </section>;
}
