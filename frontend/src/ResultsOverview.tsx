import {useEffect,useState} from "react";
import {ShieldCheck} from "lucide-react";
import {merchantApi,type ManualSaleList,type ProgramParticipant} from "./api";
import "./vf-ui.css";
import "./results-overview.css";

/* Resultados — réplica do protótipo aprovado "O que o clube trouxe": três
   números e o gráfico de novos membros por mês. Só registros do Fideliza; o que
   ainda não é medido aparece como "ainda não medido", nunca como número. */
const MAX_PAGES=10;
const monthKey=(d:Date)=>d.getFullYear()*12+d.getMonth();

export default function ResultsOverview({tenantId,onClients,onSales,onProgram}:{
 tenantId:string;onClients:()=>void;onSales:()=>void;onProgram:()=>void;
}){
 const [people,setPeople]=useState<ProgramParticipant[]|null>(null);
 const [summary,setSummary]=useState<{total:number;active:number}|null>(null);
 const [partial,setPartial]=useState(false);
 const [manual,setManual]=useState<ManualSaleList|null>(null);
 const [error,setError]=useState("");
 const [loading,setLoading]=useState(true);
 useEffect(()=>{
  let active=true;setLoading(true);setPeople(null);setManual(null);setError("");setPartial(false);
  const loadPeople=async()=>{
   const first=await merchantApi.listParticipants(tenantId,{status:"all",offset:0});
   const all=[...first.items];let page=1;
   while(all.length<first.total_filtered&&page<MAX_PAGES){
    const next=await merchantApi.listParticipants(tenantId,{status:"all",offset:all.length});
    if(!next.items.length)break;all.push(...next.items);page++;
   }
   return {all,first,partial:all.length<first.total_filtered};
  };
  Promise.allSettled([loadPeople(),merchantApi.listManualSales(tenantId)]).then(([p,s])=>{
   if(!active)return;
   if(p.status==="fulfilled"){setPeople(p.value.all);setSummary(p.value.first.summary);setPartial(p.value.partial);}
   if(s.status==="fulfilled")setManual(s.value);
   if(p.status==="rejected"||s.status==="rejected")setError("Alguns números não puderam ser consultados. Traço significa dado indisponível, não zero.");
  }).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId]);

 const sales=manual?.items??[];
 const pending=sales.filter(v=>v.state==="awaiting_review").length;
 const withoutMember=sales.filter(v=>v.state==="awaiting_member").length;
 const now=new Date();
 const months=Array.from({length:6},(_,i)=>{const d=new Date(now.getFullYear(),now.getMonth()-5+i,1);return {key:monthKey(d),
  label:d.toLocaleDateString("pt-BR",{month:"short"}).replace(".",""),count:0};});
 for(const p of people??[]){const d=new Date(p.joined_at||p.consented_at);if(Number.isNaN(d.getTime()))continue;
  const m=months.find(x=>x.key===monthKey(d));if(m)m.count++;}
 const peak=Math.max(1,...months.map(m=>m.count));
 const dash=(v:number|null|undefined)=>loading?"…":v===null||v===undefined?"—":v.toLocaleString("pt-BR");

 return <section className="vf-screen vf-results-root" aria-labelledby="vf-res-title">
  <div className="vf-head"><div><span className="vf-eyebrow">Resultados</span><h1 id="vf-res-title" className="vf-h1">O que o clube trouxe</h1></div></div>
  {error&&<div className="vf-toast is-info" role="status">{error}</div>}
  <div className="vf-grid3">
   <button type="button" className="vf-card is-lift vf-kpi vf-res-kpi" onClick={onClients}>
    <span className="vf-kpi-label">Participantes ativos</span><strong className="vf-kpi-val">{dash(summary?.active)}</strong>
    <span className="vf-muted vf-small">adesões confirmadas nesta loja</span></button>
   <button type="button" className="vf-card is-lift vf-kpi vf-res-kpi" onClick={onSales}>
    <span className="vf-kpi-label">Vendas do balcão</span><strong className="vf-kpi-val">{dash(manual?sales.length:null)}</strong>
    <span className="vf-muted vf-small">últimos 30 registros · {manual?`${pending} para conferir`:"—"}</span></button>
   <button type="button" className="vf-card is-lift vf-kpi vf-res-kpi" onClick={onProgram}>
    <span className="vf-kpi-label">Vendas sem cliente do clube</span><strong className="vf-kpi-val">{dash(manual?withoutMember:null)}</strong>
    <span className="vf-muted vf-small">oportunidade de convidar para o clube</span></button>
  </div>
  <section className="vf-card" aria-labelledby="vf-res-bars">
   <div className="vf-card-head"><h2 id="vf-res-bars" className="vf-h2">Novos membros por mês</h2>
    {partial&&<span className="vf-chip is-gold">Mostrando os {people?.length} mais recentes</span>}</div>
   {loading?<p className="vf-muted" role="status">Carregando…</p>:people===null?<p className="vf-muted">Não foi possível consultar os participantes.</p>
    :<div className="vf-cols" role="img" aria-label={"Novos membros: "+months.map(m=>`${m.label} ${m.count}`).join(", ")}>
     {months.map((m,i)=><div key={m.key} className="vf-col"><b>{m.count}</b>
      <div className="vf-col-bar" style={{height:Math.max(4,m.count/peak*130)+"px",animationDelay:i*60+"ms"}}/>
      <small>{m.label}</small></div>)}</div>}
  </section>
  <section className="vf-card vf-res-await" aria-labelledby="vf-res-money">
   <div className="vf-card-head"><div><h2 id="vf-res-money" className="vf-h2">Recompra e custo real</h2>
    <span className="vf-muted vf-small">Clientes que voltaram, descontos usados e saldo que pode virar desconto.</span></div>
    <span className="vf-chip is-soft">Ainda não medido</span></div>
   <p className="vf-note"><ShieldCheck size={16}/>Esses números aparecem quando os pedidos pagos e os pontos estiverem ligados. Até lá, não mostramos estimativa.</p>
  </section>
 </section>;
}
