import {useEffect,useState} from "react";
import {formatPhone} from "./phone-mask";
import {ArrowLeft,Cake,CheckCircle2,Copy,ExternalLink,Gift,Mail,Pause,Phone,Play,Receipt,ShoppingBag,Sparkles,Store as StoreIcon,X} from "lucide-react";
import {ApiError,merchantApi,type ParticipantDetail,type Store} from "./api";
import {initialsOf} from "./ActionCenter";
import type {SaleClient} from "./SalesWorkspace";
import "./vf-ui.css";
import ClientWhatsApp from "./ClientWhatsApp";
import "./clients.css";

/* Página própria do cliente (/app/clientes/<id>). Abre por link, então dá para
   abrir em outra aba (Ctrl/⌘ + clique). Mostra tudo da participação e as ações
   do lojista: registrar venda, celular, pausar/retomar, conferir vendas e ver
   as campanhas em que o cliente está. Nada aqui credita pontos; a mensagem pronta
   de WhatsApp só é aberta no aparelho do lojista, que escolhe o contato e envia. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const day=(iso:string|null)=>{if(!iso)return "—";const d=new Date(iso);
 return Number.isNaN(d.getTime())?"—":d.toLocaleDateString("pt-BR",{day:"2-digit",month:"short",year:"numeric"});};
const MONTHS=["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
const SALE_STATE:Record<string,[string,string]>={
 awaiting_member:["Sem cliente","is-soft"],awaiting_review:["Para conferir","is-gold"],
 verified_manual:["Conferida","is-ok"],rejected:["Rejeitada","is-danger"],
};
const CHANNEL:Record<string,string>={counter:"Balcão",nuvemshop:"Site",whatsapp:"WhatsApp",vidalys_flow:"Vidalys Flow"};

export default function ClientPage({tenantId,clientId,role,storeSlug,storeName="",onBack,onRegisterSale,onOpenSales}:{
 tenantId:string;clientId:string;role:Store["role"];storeSlug:string;storeName?:string;
 onBack:()=>void;onRegisterSale:(client:SaleClient)=>void;onOpenSales:()=>void}){
 const canManage=role==="owner"||role==="admin";
 const [data,setData]=useState<ParticipantDetail|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 const [notice,setNotice]=useState("");
 const [confirmPause,setConfirmPause]=useState(false);
 const [phoneOpen,setPhoneOpen]=useState(false);
 const [phoneValue,setPhoneValue]=useState("");
 const [phoneOk,setPhoneOk]=useState(false);
 const [version,setVersion]=useState(0);

 useEffect(()=>{
  let active=true;setLoading(true);setError("");
  merchantApi.participantDetail(tenantId,clientId).then(r=>{if(active)setData(r);})
   .catch(e=>{if(active)setError(e instanceof ApiError&&e.status===404?"Cliente não encontrado nesta loja. Ele pode ter saído do clube.":"Não foi possível carregar o cliente.");})
   .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId,clientId,version]);

 if(loading&&!data)return <section className="vf-screen" aria-busy="true"><p className="vf-muted" role="status">Carregando cliente…</p></section>;
 if(error||!data)return <section className="vf-screen">
  <button type="button" className="vf-btn is-small is-link" onClick={onBack}><ArrowLeft size={16}/> Voltar para clientes</button>
  <div className="vf-toast is-error" role="alert">{error||"Cliente indisponível."}</div></section>;

 const p=data.participant;const prof=data.profile;
 const paused=p.status==="paused";
 const points=p.points_status==="ledger_only"&&p.points_balance!==null?p.points_balance:null;
 const gift=data.program?.mode==="giftback";
 const pending=data.sales.filter(s=>s.state==="awaiting_review").length;
 const clubUrl=window.location.origin+"/clube/"+encodeURIComponent(storeSlug);

 const setStatus=async(next:"active"|"paused")=>{
  setBusy(true);setNotice("");setError("");
  try{setData(await merchantApi.setParticipantStatus(tenantId,p.id,next));setConfirmPause(false);
   setNotice(next==="paused"?"Participação pausada. Novas compras não contam até você retomar.":"Participação retomada.");}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível alterar a participação.");}
  finally{setBusy(false);}
 };
 const savePhone=async()=>{
  setBusy(true);setNotice("");setError("");
  try{await merchantApi.setParticipantPhone(tenantId,p.id,phoneValue.trim());
   setPhoneOpen(false);setPhoneOk(false);setPhoneValue("");setNotice("Celular salvo. Só os 4 últimos dígitos ficam visíveis.");setVersion(v=>v+1);}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar o celular.");}
  finally{setBusy(false);}
 };
 const copyLink=async()=>{
  try{await navigator.clipboard.writeText(clubUrl);setNotice(gift?"Link do clube copiado. Envie para o cliente acompanhar o crédito.":"Link do clube copiado. Envie para o cliente acompanhar os pontos.");}
  catch{setNotice("Link do clube: "+clubUrl);}
 };

 return <section className="vf-screen vf-client-page" aria-labelledby="vf-client-title">
  <button type="button" className="vf-btn is-small is-link vf-client-back" onClick={onBack}><ArrowLeft size={16}/> Clientes</button>

  <header className="vf-card vf-client-hero">
   <span className="vf-avatar tone-1 is-big" aria-hidden="true">{initialsOf(p.display_name)}</span>
   <div className="vf-client-id">
    <span className="vf-eyebrow">Cliente do clube</span>
    <h1 id="vf-client-title" className="vf-h1">{p.display_name||"Participante sem nome"}</h1>
    <div className="vf-client-tags">
     <span className={"vf-chip "+(paused?"is-gold":"is-ok")}>{paused?"Pausado":"Participando"}</span>
     {p.nuvemshop_customer_linked&&<span className="vf-chip is-soft">Cliente do site</span>}
     {prof.email_verified&&<span className="vf-chip is-soft"><CheckCircle2 size={13}/> E-mail confirmado</span>}
     {prof.marketing_opt_in&&<span className="vf-chip is-soft"><Mail size={13}/> Aceita ofertas</span>}
    </div>
   </div>
   {canManage&&<div className="vf-client-actions">
    <button type="button" className="vf-btn is-primary" disabled={paused} onClick={()=>onRegisterSale({id:p.id,display_name:p.display_name,detail:p.phone_last4?"Celular final "+p.phone_last4:p.contact_email})}>
     <Receipt size={17}/> Registrar venda</button>
    <button type="button" className="vf-btn" onClick={()=>void copyLink()}><Copy size={16}/> Link do clube</button>
   </div>}
  </header>

  {notice&&<div className="vf-toast" role="status"><CheckCircle2 size={18}/>{notice}</div>}
  {error&&<div className="vf-toast is-error" role="alert"><X size={18}/>{error}</div>}
  {paused&&<div className="vf-note is-warn" role="status">Participação pausada: novas vendas não podem ser registradas para este cliente até retomar.</div>}

  <div className="vf-grid4 vf-client-kpis">
   <div className="vf-kpi"><span className="vf-kpi-label">{gift?"Crédito":"Pontos"}</span>
    <strong className="vf-kpi-val">{points===null?"—":gift?money(points):points.toLocaleString("pt-BR")}</strong>
    <span className="vf-muted vf-small">{points===null?(gift?"Giftback ainda sem crédito":"Pontuação ainda não ativa"):gift?"liberado para usar":money(points)+" em descontos"}</span></div>
   <div className="vf-kpi"><span className="vf-kpi-label">Compras registradas</span><strong className="vf-kpi-val">{data.sales.length}</strong>
    <span className="vf-muted vf-small">{p.manual_sales_reviewed} conferidas no balcão</span></div>
   <div className="vf-kpi"><span className="vf-kpi-label">Valor informado</span><strong className="vf-kpi-val">{money(p.manual_sales_reported_cents)}</strong>
    <span className="vf-muted vf-small">Digitado no caixa, não é receita confirmada</span></div>
   <div className="vf-kpi"><span className="vf-kpi-label">Última atividade</span><strong className="vf-kpi-val vf-client-date">{day(p.last_program_activity_at||p.last_manual_sale_at)}</strong>
    <span className="vf-muted vf-small">No clube desde {day(p.joined_at)}</span></div>
  </div>

  <div className="vf-client-cols">
   <div className="vf-client-main">
    <section className="vf-card" aria-labelledby="vf-client-sales">
     <div className="vf-card-head"><h2 id="vf-client-sales" className="vf-h2">Compras</h2>
      {pending>0&&canManage&&<button type="button" className="vf-btn is-small" onClick={onOpenSales}>{pending} para conferir</button>}</div>
     {data.sales.length===0?<div className="vf-empty"><ShoppingBag size={22}/><p>Nenhuma compra ligada a este cliente ainda. Registre no balcão ou ligue um pedido do site.</p></div>
     :<ul className="vf-list vf-client-sales">{data.sales.map(s=>{const [label,tone]=SALE_STATE[s.state]||["Em análise","is-soft"];
      return <li key={s.id} className="vf-row">
       <span className="vf-ico tone-purple" aria-hidden="true">{s.channel==="counter"?<StoreIcon size={18}/>:<ShoppingBag size={18}/>}</span>
       <div className="vf-row-main"><strong>{money(s.amount_cents)}</strong><span>{CHANNEL[s.channel]||s.channel} · {day(s.at)} · {s.reference}</span></div>
       <span className={"vf-chip "+tone}>{label}</span></li>;})}</ul>}
    </section>

    <section className="vf-card" aria-labelledby="vf-client-offers">
     <h2 id="vf-client-offers" className="vf-h2">Campanhas para este cliente</h2>
     {data.offers.length===0?<p className="vf-muted vf-small">Nenhuma campanha no ar alcança este cliente agora.</p>
     :<ul className="vf-list">{data.offers.map(o=><li key={o.id} className="vf-row">
       <span className="vf-ico tone-gold" aria-hidden="true">{o.goal==="birthday"?<Cake size={18}/>:o.goal==="multiplier"?<Sparkles size={18}/>:<Gift size={18}/>}</span>
       <div className="vf-row-main"><strong>{o.title}</strong><span>{o.message}</span></div></li>)}</ul>}
    </section>
   </div>

   <aside className="vf-client-side">
    {!paused&&<ClientWhatsApp tenantId={tenantId} participantId={p.id} name={p.display_name} storeName={storeName}
     clubUrl={clubUrl} phoneLast4={p.phone_last4} marketing={prof.marketing_opt_in} offers={data.offers}/>}
    <section className="vf-card" aria-labelledby="vf-client-contact">
     <h2 id="vf-client-contact" className="vf-h3">Contato e perfil</h2>
     <ul className="vf-client-facts">
      <li><Mail size={16} aria-hidden="true"/><span>{p.contact_email||"E-mail não informado"}</span></li>
      <li><Phone size={16} aria-hidden="true"/><span>{p.phone_last4?"Celular final "+p.phone_last4:"Sem celular"}</span></li>
      <li><Cake size={16} aria-hidden="true"/><span>{prof.birth_day&&prof.birth_month?"Aniversário "+prof.birth_day+" "+MONTHS[prof.birth_month-1]:"Aniversário não informado"}</span></li>
      <li><CheckCircle2 size={16} aria-hidden="true"/><span>Regulamento {prof.terms_version} · {p.consent_channel==="customer_portal"?"aceite no Meu Clube":"aceite no site da loja"}</span></li>
     </ul>
     {canManage&&!phoneOpen&&<button type="button" className="vf-btn is-small" onClick={()=>setPhoneOpen(true)}><Phone size={15}/> {p.phone_last4?"Trocar celular":"Cadastrar celular"}</button>}
     {phoneOpen&&<form className="vf-client-phone-form" onSubmit={e=>{e.preventDefault();void savePhone();}}>
      <label className="vf-field is-compact">Celular com DDD<input type="tel" inputMode="tel" maxLength={20} placeholder="(31) 99999-9999"
       value={phoneValue} onChange={e=>setPhoneValue(formatPhone(e.target.value))}/></label>
      <label className="vf-client-phone-check"><input type="checkbox" checked={phoneOk} onChange={e=>setPhoneOk(e.target.checked)}/>
       O próprio cliente me informou este número</label>
      <div className="vf-pills"><button type="button" className="vf-btn is-small" onClick={()=>setPhoneOpen(false)}>Cancelar</button>
       <button type="submit" className="vf-btn is-small is-primary" disabled={busy||!phoneOk||!phoneValue.trim()}>{busy?"Salvando…":"Salvar celular"}</button></div>
     </form>}
    </section>

    {canManage&&<section className="vf-card" aria-labelledby="vf-client-manage">
     <h2 id="vf-client-manage" className="vf-h3">Participação</h2>
     {paused?<button type="button" className="vf-btn is-small is-primary" disabled={busy} onClick={()=>void setStatus("active")}><Play size={15}/> Retomar participação</button>
     :confirmPause?<div className="vf-client-confirm" role="group" aria-label="Confirmar pausa"><span className="vf-small">Pausar? Novas compras deixam de contar até retomar.</span>
       <button type="button" className="vf-btn is-small" onClick={()=>setConfirmPause(false)}>Cancelar</button>
       <button type="button" className="vf-btn is-small is-danger" disabled={busy} onClick={()=>void setStatus("paused")}>Confirmar pausa</button></div>
     :<button type="button" className="vf-btn is-small" onClick={()=>setConfirmPause(true)}><Pause size={15}/> Pausar participação</button>}
     <p className="vf-muted vf-small">Sair do clube e apagar dados é pedido pelo próprio cliente, no Meu Clube.</p>
     <a className="vf-btn is-small is-link" href={clubUrl} target="_blank" rel="noreferrer"><ExternalLink size={15}/> Abrir a página do clube</a>
    </section>}
   </aside>
  </div>
 </section>;
}
