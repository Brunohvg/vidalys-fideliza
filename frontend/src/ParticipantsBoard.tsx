import {useEffect,useState,type FormEvent,type MouseEvent} from "react";
import {ChevronLeft,ChevronRight,RefreshCw,Search,UserPlus} from "lucide-react";
import {ApiError,merchantApi,type ParticipantDirectoryResponse,type ProgramParticipant,type Store} from "./api";
import {initialsOf} from "./ActionCenter";
import ClientPage from "./ClientPage";
import {clientIdFromPath,clientPath,merchantPaths} from "./routes";
import type {SaleClient} from "./SalesWorkspace";
import "./vf-ui.css";
import "./clients.css";

/* Clientes — réplica do protótipo aprovado "Quem faz parte do clube": selos de
   filtro, busca e tabela com avatar, saldo, situação e canal. Só aparece quem
   confirmou a adesão; saldo sem pontos ativos aparece como "—". */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const day=(iso:string|null)=>{if(!iso)return "—";const d=new Date(iso);
 return Number.isNaN(d.getTime())?"—":d.toLocaleDateString("pt-BR",{day:"2-digit",month:"short",year:"numeric"});};
const name=(p:ProgramParticipant)=>p.display_name||"Participante sem nome";
const channel=(p:ProgramParticipant)=>p.nuvemshop_customer_linked||p.consent_channel==="storefront_opt_in"?"Site":p.manual_sales_count>0?"Balcão":"Convite";
const TONES=["tone-1","tone-2","tone-3","tone-4","tone-5"];

export default function ParticipantsBoard({tenantId,onOpenProgram,initialSearch="",role,storeSlug,onRegisterSale,onOpenSales}:{
 tenantId:string;onOpenProgram:()=>void;initialSearch?:string;role:Store["role"];storeSlug:string;
 onRegisterSale:(client:SaleClient)=>void;onOpenSales:()=>void}){
 const [clientId,setClientId]=useState(()=>clientIdFromPath(window.location.pathname));
 useEffect(()=>{
  const sync=()=>setClientId(clientIdFromPath(window.location.pathname));
  window.addEventListener("popstate",sync);window.addEventListener("fideliza:route",sync);
  return()=>{window.removeEventListener("popstate",sync);window.removeEventListener("fideliza:route",sync);};
 },[]);
 // Clique normal abre a página do cliente aqui; Ctrl/⌘/botão do meio abre em outra aba.
 const openClient=(event:MouseEvent,id:string)=>{
  if(event.metaKey||event.ctrlKey||event.shiftKey||event.button!==0)return;
  event.preventDefault();
  window.history.pushState(null,"",clientPath(id));setClientId(id);window.scrollTo({top:0});
 };
 const backToList=()=>{window.history.pushState(null,"",merchantPaths.clients);setClientId(null);};
 const [data,setData]=useState<ParticipantDirectoryResponse|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 const [text,setText]=useState(initialSearch);
 const [search,setSearch]=useState(initialSearch);
 const [status,setStatus]=useState<"all"|"active"|"paused">("all");
 const [offset,setOffset]=useState(0);
 const [version,setVersion]=useState(0);

 useEffect(()=>{
  if(clientId)return; // Na página do cliente a lista não é carregada.
  let active=true;setLoading(true);setError("");
  merchantApi.listParticipants(tenantId,{q:search,status,offset}).then(r=>{if(active){setData(r);setLoading(false);}})
   .catch(e=>{if(active){setError(e instanceof ApiError?e.message:"Falha ao carregar participantes.");setLoading(false);}});
  return()=>{active=false};
 },[tenantId,search,status,offset,version,clientId]);

 const submit=(e:FormEvent)=>{e.preventDefault();setOffset(0);setSearch(text.trim());};
 const balance=(p:ProgramParticipant)=>p.points_status==="ledger_only"&&p.points_balance!==null?p.points_balance:null;
 const filters:[typeof status,string,number|undefined][]=[["all","Todos",data?.summary.total],["active","Participando",data?.summary.active],["paused","Pausados",data?.summary.paused]];

 if(clientId)return <ClientPage tenantId={tenantId} clientId={clientId} role={role} storeSlug={storeSlug}
  onBack={backToList} onRegisterSale={onRegisterSale} onOpenSales={onOpenSales} key={clientId}/>;

 return <section className="vf-screen vf-clients" aria-labelledby="vf-clients-title">
  <div className="vf-head">
   <div><span className="vf-eyebrow">Clientes</span><h1 id="vf-clients-title" className="vf-h1">Quem faz parte do clube</h1></div>
   <div className="vf-pills" role="group" aria-label="Filtrar participantes">
    {filters.map(([key,label,count])=><button key={key} type="button" className={"vf-chip "+(key==="paused"?"is-gold":"is-soft")}
     aria-pressed={status===key} onClick={()=>{setStatus(key);setOffset(0);}}>{label} · {count??"—"}</button>)}
   </div>
  </div>
  <div className="vf-clients-bar">
   <form className="vf-clients-search" role="search" onSubmit={submit}>
    <Search size={18} aria-hidden="true"/>
    <input aria-label="Buscar participantes" maxLength={80} placeholder="Buscar por nome ou e-mail" value={text} onChange={e=>setText(e.target.value)}/>
    <button type="submit" className="vf-btn is-small">Buscar</button>
   </form>
   <button type="button" className="vf-btn is-small" disabled={loading} onClick={()=>setVersion(v=>v+1)}><RefreshCw size={16}/> Atualizar</button>
   <button type="button" className="vf-btn is-small is-primary" onClick={onOpenProgram}><UserPlus size={16}/> Gerenciar adesões</button>
  </div>
  {error&&<div className="vf-toast is-error" role="alert">{error} <button type="button" className="vf-btn is-small" onClick={()=>setVersion(v=>v+1)}>Tentar novamente</button></div>}

  <div className="vf-card is-flush">
   {loading?<p className="vf-clients-msg vf-muted" role="status">Carregando participantes…</p>
    :data&&data.items.length===0?<div className="vf-clients-msg vf-empty">
      <strong className="vf-h3">{data.summary.total===0?"Seu clube começa com o primeiro cliente":"Ninguém encontrado"}</strong>
      <p>{data.summary.total===0?"Compartilhe o link de convite no caixa, no Instagram e no WhatsApp. Só entra quem aceita o regulamento."
       :"Ajuste a busca ou o filtro."}</p>
      {data.summary.total===0&&<button type="button" className="vf-btn is-primary" onClick={onOpenProgram}>Compartilhar convite</button>}
     </div>
    :data&&<>
     <div className="vf-table-box vf-clients-table">
      <table className="vf-table"><thead><tr><th>Cliente</th><th>Saldo</th><th>Vale</th><th>Situação</th><th>Desde</th><th>Canal</th><th><span className="vf-sr">Ações</span></th></tr></thead>
       <tbody>{data.items.map((p,i)=>{const b=balance(p);return <tr key={p.id}>
        <td><div className="vf-clients-person"><span className={"vf-avatar "+TONES[i%5]} aria-hidden="true">{initialsOf(p.display_name)}</span>
         <div><strong>{name(p)}</strong><span className="vf-muted">{p.contact_email||"Contato não informado"}</span></div></div></td>
        <td className="vf-num"><strong>{b===null?"—":b.toLocaleString("pt-BR")+" pts"}</strong></td>
        <td className="vf-muted vf-num">{b===null?"—":money(b)}</td>
        <td><span className={"vf-chip "+(p.status==="active"?"is-ok":"is-gold")}>{p.status==="active"?"Participando":"Pausado"}</span>
         {p.manual_sales_pending>0&&<span className="vf-chip is-soft vf-clients-pending">{p.manual_sales_pending} p/ conferir</span>}</td>
        <td className="vf-muted">{day(p.joined_at||p.consented_at)}</td>
        <td className="vf-muted">{channel(p)}</td>
        <td><a className="vf-btn is-small" href={clientPath(p.id)} onClick={e=>openClient(e,p.id)}
         aria-label={"Abrir "+name(p)}>Abrir</a></td>
       </tr>;})}</tbody></table>
     </div>
     <ul className="vf-clients-cards" aria-label="Participantes encontrados">
      {data.items.map((p,i)=>{const b=balance(p);return <li key={p.id}>
       <a href={clientPath(p.id)} onClick={e=>openClient(e,p.id)}>
        <span className={"vf-avatar "+TONES[i%5]} aria-hidden="true">{initialsOf(p.display_name)}</span>
        <span className="vf-row-main"><strong>{name(p)}</strong><span>{channel(p)} · desde {day(p.joined_at||p.consented_at)}</span></span>
        <span className="vf-clients-card-pts"><strong>{b===null?"—":b.toLocaleString("pt-BR")+" pts"}</strong>
         <span className={"vf-chip "+(p.status==="active"?"is-ok":"is-gold")}>{p.status==="active"?"Ativo":"Pausado"}</span></span>
       </a></li>;})}
     </ul>
     {data.total_filtered>0&&<div className="vf-clients-pages">
      <span className="vf-muted vf-small">{data.total_filtered} participante{data.total_filtered===1?"":"s"}</span>
      <div><button type="button" className="vf-btn is-small" aria-label="Página anterior" disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-20))}><ChevronLeft size={18}/></button>
       <span className="vf-small">{Math.floor(offset/20)+1}</span>
       <button type="button" className="vf-btn is-small" aria-label="Próxima página" disabled={offset+20>=data.total_filtered} onClick={()=>setOffset(n=>n+20)}><ChevronRight size={18}/></button></div>
     </div>}
    </>}
  </div>

 </section>;
}
