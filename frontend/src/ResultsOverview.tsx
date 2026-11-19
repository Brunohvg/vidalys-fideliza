import {useEffect,useState} from "react";
import {ArrowUpRight,ShieldCheck,ShoppingBag,Users,Wallet,Receipt} from "lucide-react";
import {ApiError,merchantApi,type ClubResults,type ProgramParticipant} from "./api";
import "./vf-ui.css";
import "./results-overview.css";

/* Resultados — "O que o clube trouxe", só com registros reais do Fideliza:
   vendas do clube, quem voltou, desconto concedido e custo real, saldo com as clientes,
   emitido x usado por mês e para onde foi o saldo. Sem grupo de controle, a tela
   descreve o que aconteceu e NÃO afirma que o clube causou as vendas. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const short=(cents:number)=>cents>=100000?"R$ "+(cents/100000).toLocaleString("pt-BR",{maximumFractionDigits:1})+" mil":money(cents);
const pts=(n:number)=>n.toLocaleString("pt-BR");
const pct=(part:number,total:number)=>total?Math.round(part*100/total):0;
const monthLabel=(iso:string)=>new Date(iso+"T12:00:00").toLocaleDateString("pt-BR",{month:"short"}).replace(".","");
/* Paleta categórica validada (scripts/validate_palette.js, modo claro): ordem fixa, nunca reciclada. */
const C={used:"#6A3DF0",open:"#E0A100",expired:"#D4577A",reversed:"#1F8FB8"};
const MAX_PAGES=10;
const monthKey=(d:Date)=>d.getFullYear()*12+d.getMonth();

export default function ResultsOverview({tenantId,onClients,onSales,onProgram}:{
 tenantId:string;onClients:()=>void;onSales:()=>void;onProgram:()=>void;
}){
 const [days,setDays]=useState<30|90>(30);
 const [data,setData]=useState<ClubResults|null>(null);
 const [people,setPeople]=useState<ProgramParticipant[]|null>(null);
 const [error,setError]=useState("");
 const [loading,setLoading]=useState(true);
 const [hover,setHover]=useState<number|null>(null);

 useEffect(()=>{
  let active=true;setLoading(true);setError("");
  merchantApi.clubResults(tenantId,days).then(r=>{if(active)setData(r);})
   .catch(e=>{if(active){setData(null);setError(e instanceof ApiError?e.message:"Não foi possível consultar os resultados.");}})
   .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId,days]);

 useEffect(()=>{
  let active=true;
  (async()=>{
   const first=await merchantApi.listParticipants(tenantId,{status:"all",offset:0});
   const all=[...first.items];let page=1;
   while(all.length<first.total_filtered&&page<MAX_PAGES){
    const next=await merchantApi.listParticipants(tenantId,{status:"all",offset:all.length});
    if(!next.items.length)break;all.push(...next.items);page++;
   }
   if(active)setPeople(all);
  })().catch(()=>{if(active)setPeople(null);});
  return()=>{active=false};
 },[tenantId]);

 const gift=data?.program.mode==="giftback";
 const unit=(n:number)=>gift?money(n):pts(n)+" pts";
 const openNow=data?data.open.available+data.open.reserved:0;
 const periodOpen=data?Math.max(0,data.issued-data.used-data.expired-data.reversed):0;
 const flow=data?[["used","Usado",data.used],["open","Ainda com as clientes",periodOpen],["expired","Venceu",data.expired],["reversed","Estornado",data.reversed]] as const:[];
 const flowTotal=flow.reduce((s,[, ,v])=>s+v,0);
 const peak=data?Math.max(1,...data.months.flatMap(m=>[m.issued,m.used])):1;
 const now=new Date();
 const joins=Array.from({length:6},(_,i)=>{const d=new Date(now.getFullYear(),now.getMonth()-5+i,1);return {key:monthKey(d),
  label:d.toLocaleDateString("pt-BR",{month:"short"}).replace(".",""),count:0};});
 for(const p of people??[]){const d=new Date(p.joined_at||p.consented_at);if(Number.isNaN(d.getTime()))continue;
  const m=joins.find(x=>x.key===monthKey(d));if(m)m.count++;}
 const joinPeak=Math.max(1,...joins.map(m=>m.count));
 const empty=data&&data.purchases===0;

 return <section className="vf-screen vf-results-root" aria-labelledby="vf-res-title">
  <div className="vf-head vr-head"><div><span className="vf-eyebrow">Resultados</span><h1 id="vf-res-title" className="vf-h1">O que o clube trouxe</h1></div>
   <div className="vr-period" role="group" aria-label="Período">
    {([30,90] as const).map(d=><button key={d} type="button" aria-pressed={days===d} className={days===d?"is-on":""} onClick={()=>setDays(d)}>{d} dias</button>)}
   </div></div>
  {error&&<div className="vf-toast is-error" role="alert">{error}</div>}

  <div className="vr-kpis">
   <button type="button" className="vf-card is-lift vr-kpi" onClick={onSales}>
    <span className="vr-kpi-top"><span className="vr-ico" aria-hidden="true"><ShoppingBag size={18}/></span>Vendas do clube</span>
    <strong>{loading?"…":data?short(data.revenue_cents):"—"}</strong>
    <small>{data?`${pts(data.purchases)} compra${data.purchases===1?"":"s"} de clientes do clube`:"—"}</small></button>
   <button type="button" className="vf-card is-lift vr-kpi" onClick={onClients}>
    <span className="vr-kpi-top"><span className="vr-ico" aria-hidden="true"><Users size={18}/></span>Clientes que voltaram</span>
    <strong>{loading?"…":data?`${pts(data.came_back)}`:"—"}<em>{data&&data.buyers?` de ${pts(data.buyers)}`:""}</em></strong>
    <small>{data&&data.buyers?`${pct(data.came_back,data.buyers)}% compraram mais de uma vez`:"aparece com as primeiras compras"}</small></button>
   <button type="button" className="vf-card is-lift vr-kpi" onClick={onProgram}>
    <span className="vr-kpi-top"><span className="vr-ico" aria-hidden="true"><Receipt size={18}/></span>Desconto concedido</span>
    <strong>{loading?"…":data?money(data.discount_cents):"—"}</strong>
    <small>{data?.cost_bps!=null?`custo real: ${(data.cost_bps/100).toLocaleString("pt-BR")}% das vendas do clube`:"custo real aparece com vendas"}</small></button>
   <button type="button" className="vf-card is-lift vr-kpi" onClick={onProgram}>
    <span className="vr-kpi-top"><span className="vr-ico" aria-hidden="true"><Wallet size={18}/></span>{gift?"Crédito com as clientes":"Saldo com as clientes"}</span>
    <strong>{loading?"…":data?(gift?money(openNow):pts(openNow)):"—"}</strong>
    <small>{data?(data.open.pending?`+ ${unit(data.open.pending)} a liberar · `:"")+"pode virar desconto":"—"}</small></button>
  </div>

  {empty&&<section className="vf-card vr-empty">
   <span className="vr-ico is-big" aria-hidden="true"><ArrowUpRight size={22}/></span>
   <div><strong>Ainda não há compras do clube nos últimos {days} dias</strong>
    <span>Os números aparecem quando vendas de clientes do clube forem confirmadas no balcão ou pagas no site, com o clube ativo em Meu clube.</span></div>
   <button type="button" className="vf-btn is-small" onClick={onProgram}>Abrir Meu clube</button>
  </section>}

  {data&&!empty&&<div className="vr-grid">
   <section className="vf-card vr-card" aria-labelledby="vr-months-title">
    <div className="vf-card-head"><div><h2 id="vr-months-title" className="vf-h2">{gift?"Crédito gerado e usado":"Pontos gerados e usados"}</h2>
     <span className="vf-muted vf-small">Últimos 6 meses</span></div>
     <ul className="vr-legend" aria-label="Legenda"><li><i style={{background:C.used}}/>Usado</li><li><i className="is-issued"/>Gerado</li></ul></div>
    <div className="vr-bars" role="img" aria-label={data.months.map(m=>`${monthLabel(m.month)}: gerado ${unit(m.issued)}, usado ${unit(m.used)}`).join("; ")}
     onMouseLeave={()=>setHover(null)}>
     {data.months.map((m,i)=><div key={m.month} className={"vr-month"+(hover===i?" is-hover":"")} onMouseEnter={()=>setHover(i)}
      onFocus={()=>setHover(i)} onBlur={()=>setHover(null)} tabIndex={0} aria-label={`${monthLabel(m.month)}: gerado ${unit(m.issued)}, usado ${unit(m.used)}`}>
      <div className="vr-pair">
       <span className="vr-bar is-issued" style={{height:Math.max(m.issued?4:2,m.issued/peak*150)+"px"}}/>
       <span className="vr-bar" style={{height:Math.max(m.used?4:2,m.used/peak*150)+"px",background:C.used}}/>
      </div>
      <small>{monthLabel(m.month)}</small>
      {hover===i&&<span className="vr-tip" role="tooltip"><b>{monthLabel(m.month)}</b>Gerado {unit(m.issued)}<br/>Usado {unit(m.used)}</span>}
     </div>)}
    </div>
    <table className="vf-sr"><caption>Gerado e usado por mês</caption><thead><tr><th>Mês</th><th>Gerado</th><th>Usado</th></tr></thead>
     <tbody>{data.months.map(m=><tr key={m.month}><td>{monthLabel(m.month)}</td><td>{unit(m.issued)}</td><td>{unit(m.used)}</td></tr>)}</tbody></table>
   </section>

   <section className="vf-card vr-card" aria-labelledby="vr-flow-title">
    <div className="vf-card-head"><div><h2 id="vr-flow-title" className="vf-h2">Para onde foi {gift?"o crédito":"o saldo"} do período</h2>
     <span className="vf-muted vf-small">{unit(data.issued)} gerado{gift?"":"s"} nos últimos {days} dias</span></div></div>
    <div className="vr-stack" role="img" aria-label={flow.map(([,l,v])=>`${l}: ${unit(v)}`).join("; ")}>
     {flow.filter(([, ,v])=>v>0).map(([k,l,v])=><span key={k} style={{flexGrow:v,background:C[k]}} title={`${l}: ${unit(v)}`}/>)}
     {flowTotal===0&&<span className="is-empty"/>}
    </div>
    <ul className="vr-flow">{flow.map(([k,l,v])=><li key={k}><i style={{background:C[k]}}/><span>{l}</span>
     <b>{unit(v)}</b><small>{pct(v,flowTotal)}%</small></li>)}</ul>
    {data.pulled_revenue_cents>0&&<p className="vr-pulled"><ArrowUpRight size={16} aria-hidden="true"/>
     <span>Compras em que a cliente usou {gift?"crédito":"um vale"} somaram <b>{money(data.pulled_revenue_cents)}</b>, para {money(data.discount_cents)} de desconto.</span></p>}
   </section>

   <section className="vf-card vr-card" aria-labelledby="vr-counter-title">
    <div className="vf-card-head"><div><h2 id="vr-counter-title" className="vf-h2">Balcão: clube e fora do clube</h2>
     <span className="vf-muted vf-small">{pts(data.counter.sales)} vendas registradas · {pct(data.counter.with_member,data.counter.sales)}% com cliente do clube</span></div></div>
    {(()=>{const total=data.counter.member_cents+data.counter.other_cents;return <>
     <div className="vr-stack is-two" role="img" aria-label={`Clube ${money(data.counter.member_cents)}, fora do clube ${money(data.counter.other_cents)}`}>
      {data.counter.member_cents>0&&<span style={{flexGrow:data.counter.member_cents,background:C.used}}/>}
      {data.counter.other_cents>0&&<span className="is-other" style={{flexGrow:data.counter.other_cents}}/>}
      {total===0&&<span className="is-empty"/>}
     </div>
     <ul className="vr-flow"><li><i style={{background:C.used}}/><span>Clientes do clube</span><b>{money(data.counter.member_cents)}</b><small>{pct(data.counter.member_cents,total)}%</small></li>
      <li><i className="is-other"/><span>Fora do clube</span><b>{money(data.counter.other_cents)}</b><small>{pct(data.counter.other_cents,total)}%</small></li></ul>
     {data.counter.other_cents>0&&<p className="vf-muted vf-small">Cada venda fora do clube é uma chance de convite: peça o celular no caixa.</p>}
    </>;})()}
   </section>

   <section className="vf-card vr-card" aria-labelledby="vf-res-bars">
    <div className="vf-card-head"><div><h2 id="vf-res-bars" className="vf-h2">Novos membros por mês</h2>
     <span className="vf-muted vf-small">{pts(data.members_active)} participantes ativos hoje</span></div></div>
    {people===null?<p className="vf-muted">Não foi possível consultar os participantes.</p>
     :<div className="vf-cols" role="img" aria-label={"Novos membros: "+joins.map(m=>`${m.label} ${m.count}`).join(", ")}>
      {joins.map((m,i)=><div key={m.key} className="vf-col"><b>{m.count}</b>
       <div className="vf-col-bar" style={{height:Math.max(4,m.count/joinPeak*130)+"px",animationDelay:i*60+"ms"}}/>
       <small>{m.label}</small></div>)}</div>}
   </section>
  </div>}

  <p className="vf-note vr-note"><ShieldCheck size={16}/>Só registros reais do Fideliza: compras confirmadas no balcão e pedidos pagos no site de clientes do clube.
   Sem um grupo de comparação, estes números mostram o que aconteceu no clube; não provam que o clube causou as vendas.</p>
 </section>;
}
