import {useEffect,useState} from "react";
import {ArrowRight,BarChart3,Clock3,Gift,ShieldCheck,UsersRound} from "lucide-react";
import {merchantApi,type ManualSaleList,type ParticipantDirectoryResponse} from "./api";
import "./results-overview.css";

export default function ResultsOverview({tenantId,onClients,onSales,onProgram}:{
 tenantId:string;onClients:()=>void;onSales:()=>void;onProgram:()=>void;
}){
 const [people,setPeople]=useState<ParticipantDirectoryResponse|null>(null);
 const [manual,setManual]=useState<ManualSaleList|null>(null);
 const [error,setError]=useState("");
 const [loading,setLoading]=useState(true);
 useEffect(()=>{
  let active=true;setLoading(true);setPeople(null);setManual(null);setError("");
  Promise.allSettled([
   merchantApi.listParticipants(tenantId),merchantApi.listManualSales(tenantId),
  ]).then(([p,s])=>{
   if(!active)return;
   if(p.status==="fulfilled")setPeople(p.value);
   if(s.status==="fulfilled")setManual(s.value);
   if(p.status==="rejected"||s.status==="rejected")
    setError("Alguns indicadores não puderam ser consultados nesta conta. Traços significam dados indisponíveis, não zero.");
  }).finally(()=>{if(active)setLoading(false)});
  return()=>{active=false};
 },[tenantId]);
 const recent=manual?.items??[];
 const pending=recent.filter(v=>v.state==="awaiting_review").length;
 const withoutMember=recent.filter(v=>v.state==="awaiting_member").length;
 return <div className="vf-results-root">
  <section className="vf-results-hero">
   <div><span className="portal-eyebrow">INDICADORES VERIFICADOS</span>
    <h2>Seu clube em números que fazem sentido.</h2>
    <p>Mostramos apenas registros do Fideliza. A integração de pedidos pagos e o cálculo financeiro ainda estão em desenvolvimento.</p></div>
   <BarChart3 size={44} aria-hidden="true"/>
  </section>
  {error&&<div className="vf-results-warning" role="status">{error}</div>}
  <div className="vf-results-stats">
   <article><UsersRound size={23}/><span>Participantes ativos</span>
    <strong>{loading?"…":people?.summary.active??"—"}</strong>
    <small>Adesão confirmada nesta loja</small>
    <button onClick={onClients} type="button">Ver participantes <ArrowRight size={16}/></button>
   </article>
   <article><Gift size={23}/><span>Vendas de balcão registradas</span>
    <strong>{loading?"…":manual?recent.length:"—"}</strong>
    <small>Até 30 registros recentes, não representa o total da loja</small>
    <button onClick={onSales} type="button">Ver histórico <ArrowRight size={16}/></button>
   </article>
   <article><Clock3 size={23}/><span>Aguardando conferência</span>
    <strong>{loading?"…":manual?pending:"—"}</strong>
    <small>Entre os últimos 30 registros de balcão</small>
    <button onClick={onSales} type="button">Conferir vendas <ArrowRight size={16}/></button>
   </article>
  </div>
  <div className="vf-results-lower">
   <section className="vf-results-panel">
    <h3>Oportunidades de adesão</h3>
    <p>Compras manuais registradas sem participante, nas últimas 30 entradas consultadas.</p>
    <strong>{loading?"…":manual?withoutMember:"—"}</strong>
    <button onClick={onProgram} type="button">Compartilhar o clube <ArrowRight size={16}/></button>
   </section>
   <section className="vf-results-panel">
    <h3>Resultado financeiro do programa</h3>
    <p>Compras pagas atribuídas, pontos concedidos, resgates e custo real.</p>
    <strong className="vf-results-await">Ainda não medido</strong>
    <p><ShieldCheck size={15}/> Não confundimos cadastro, pedido criado e venda efetivamente paga.</p>
   </section>
  </div>
 </div>;
}