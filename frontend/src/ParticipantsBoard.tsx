import {useEffect,useState,type FormEvent} from "react";
import {ChevronLeft,ChevronRight,RefreshCw,Search,UserPlus,X} from "lucide-react";
import {ApiError,merchantApi,type CashbackWalletView,type ParticipantDirectoryResponse,type ProgramParticipant} from "./api";
import {initialsOf} from "./ActionCenter";
import "./vf-ui.css";
import "./wallet-details.css";
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
const movements:Record<CashbackWalletView["events"][number]["kind"],string>={
 accrual:"Crédito pendente",release:"Liberação interna",reserve:"Reserva interna",cancel_reservation:"Reserva cancelada",
 redeem:"Resgate registrado",expire:"Crédito expirado",reverse_pending:"Estorno pendente",reverse_available:"Estorno de saldo liberado"};

export default function ParticipantsBoard({tenantId,onOpenProgram,initialSearch="",canManage=false}:{tenantId:string;onOpenProgram:()=>void;initialSearch?:string;canManage?:boolean}){
 const [data,setData]=useState<ParticipantDirectoryResponse|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 const [text,setText]=useState(initialSearch);
 const [search,setSearch]=useState(initialSearch);
 const [status,setStatus]=useState<"all"|"active"|"paused">("all");
 const [offset,setOffset]=useState(0);
 const [version,setVersion]=useState(0);
 const [profile,setProfile]=useState<ProgramParticipant|null>(null);
 const [wallet,setWallet]=useState<CashbackWalletView|null>(null);
 const [walletState,setWalletState]=useState<"idle"|"loading"|"error">("idle");
 const [phoneOpen,setPhoneOpen]=useState(false);
 const [phoneValue,setPhoneValue]=useState("");
 const [phoneOk,setPhoneOk]=useState(false);
 const [phoneBusy,setPhoneBusy]=useState(false);
 const [phoneMsg,setPhoneMsg]=useState("");

 useEffect(()=>{
  let active=true;setLoading(true);setError("");
  merchantApi.listParticipants(tenantId,{q:search,status,offset}).then(r=>{if(active){setData(r);setLoading(false);}})
   .catch(e=>{if(active){setError(e instanceof ApiError?e.message:"Falha ao carregar participantes.");setLoading(false);}});
  return()=>{active=false};
 },[tenantId,search,status,offset,version]);
 useEffect(()=>{setProfile(null);},[tenantId]);

 const submit=(e:FormEvent)=>{e.preventDefault();setOffset(0);setSearch(text.trim());};
 const openProfile=(p:ProgramParticipant)=>{setProfile(p);setWallet(null);setWalletState("idle");setPhoneOpen(false);setPhoneMsg("");};
 const savePhone=async()=>{
  if(!profile||phoneBusy)return;setPhoneBusy(true);setPhoneMsg("");
  try{
   const r=await merchantApi.setParticipantPhone(tenantId,profile.id,phoneValue.trim());
   setProfile({...profile,phone_last4:r.participant.phone_last4});
   setPhoneOpen(false);setPhoneOk(false);setPhoneMsg("✓ Celular salvo. Só os 4 últimos dígitos ficam visíveis.");setVersion(v=>v+1);
  }catch(e){setPhoneMsg(e instanceof ApiError?e.message:"Não foi possível salvar o celular.");}
  finally{setPhoneBusy(false);}
 };
 const openWallet=async(p:ProgramParticipant)=>{
  setWalletState("loading");
  try{setWallet(await merchantApi.participantWallet(tenantId,p.id));setWalletState("idle");}catch{setWalletState("error");}
 };
 const balance=(p:ProgramParticipant)=>p.points_status==="ledger_only"&&p.points_balance!==null?p.points_balance:null;
 const filters:[typeof status,string,number|undefined][]=[["all","Todos",data?.summary.total],["active","Participando",data?.summary.active],["paused","Pausados",data?.summary.paused]];

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
        <td><button type="button" className="vf-btn is-small" onClick={()=>openProfile(p)}>Ver</button></td>
       </tr>;})}</tbody></table>
     </div>
     <ul className="vf-clients-cards" aria-label="Participantes encontrados">
      {data.items.map((p,i)=>{const b=balance(p);return <li key={p.id}>
       <button type="button" onClick={()=>openProfile(p)}>
        <span className={"vf-avatar "+TONES[i%5]} aria-hidden="true">{initialsOf(p.display_name)}</span>
        <span className="vf-row-main"><strong>{name(p)}</strong><span>{channel(p)} · desde {day(p.joined_at||p.consented_at)}</span></span>
        <span className="vf-clients-card-pts"><strong>{b===null?"—":b.toLocaleString("pt-BR")+" pts"}</strong>
         <span className={"vf-chip "+(p.status==="active"?"is-ok":"is-gold")}>{p.status==="active"?"Ativo":"Pausado"}</span></span>
       </button></li>;})}
     </ul>
     {data.total_filtered>0&&<div className="vf-clients-pages">
      <span className="vf-muted vf-small">{data.total_filtered} participante{data.total_filtered===1?"":"s"}</span>
      <div><button type="button" className="vf-btn is-small" aria-label="Página anterior" disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-20))}><ChevronLeft size={18}/></button>
       <span className="vf-small">{Math.floor(offset/20)+1}</span>
       <button type="button" className="vf-btn is-small" aria-label="Próxima página" disabled={offset+20>=data.total_filtered} onClick={()=>setOffset(n=>n+20)}><ChevronRight size={18}/></button></div>
     </div>}
    </>}
  </div>

  {profile&&<section className="vf-card vf-client-profile" aria-label="Detalhes do participante">
   <div className="vf-card-head">
    <div className="vf-clients-person"><span className="vf-avatar tone-1" aria-hidden="true">{initialsOf(profile.display_name)}</span>
     <div><h2 className="vf-h2">{name(profile)}</h2><span className="vf-muted">{profile.contact_email||"Contato não informado"}</span></div></div>
    <button type="button" className="vf-btn is-small" onClick={()=>setProfile(null)}><X size={16}/> Fechar detalhes</button>
   </div>
   <div className="vf-grid4">
    <div className="vf-kpi"><span className="vf-kpi-label">Saldo de pontos</span><strong className="vf-kpi-val">{balance(profile)?.toLocaleString("pt-BR")??"—"}</strong>
     <span className="vf-muted vf-small">{profile.points_status==="ledger_only"?`${profile.points_pending??0} pendentes`:"Pontos ainda não ativos"}</span></div>
    <div className="vf-kpi"><span className="vf-kpi-label">Vendas no balcão</span><strong className="vf-kpi-val">{profile.manual_sales_count??0}</strong>
     <span className="vf-muted vf-small">{profile.manual_sales_reviewed??0} conferidas · {profile.manual_sales_pending??0} pendentes</span></div>
    <div className="vf-kpi"><span className="vf-kpi-label">Valor informado</span><strong className="vf-kpi-val">{money(profile.manual_sales_reported_cents??0)}</strong>
     <span className="vf-muted vf-small">Digitado no balcão, não é receita confirmada</span></div>
    <div className="vf-kpi"><span className="vf-kpi-label">Última atividade</span><strong className="vf-kpi-val vf-client-date">{day(profile.last_program_activity_at||profile.last_manual_sale_at)}</strong>
     <span className="vf-muted vf-small">{profile.nuvemshop_customer_linked?"Cliente da loja online vinculado":"Sem vínculo com a loja online"}</span></div>
   </div>
   <div className="vf-client-phone">
    <div className="vf-row-main"><strong>Celular</strong>
     <span>{profile.phone_last4?`Final ${profile.phone_last4}. No caixa, basta digitar o número para achar o cliente.`
      :"Sem celular. Cadastre para achar o cliente no caixa pelo número."}</span></div>
    {canManage&&!phoneOpen&&<button type="button" className="vf-btn is-small" onClick={()=>{setPhoneOpen(true);setPhoneValue("");setPhoneMsg("");}}>
     {profile.phone_last4?"Trocar celular":"Cadastrar celular"}</button>}
   </div>
   {phoneOpen&&<form className="vf-client-phone-form" onSubmit={e=>{e.preventDefault();void savePhone();}}>
    <label className="vf-field is-compact">Celular com DDD<input type="tel" inputMode="tel" maxLength={20} placeholder="(31) 99999-9999"
     value={phoneValue} onChange={e=>setPhoneValue(e.target.value)}/></label>
    <label className="vf-client-phone-check"><input type="checkbox" checked={phoneOk} onChange={e=>setPhoneOk(e.target.checked)}/>
     O próprio cliente me informou este número</label>
    <div className="vf-pills"><button type="button" className="vf-btn is-small" onClick={()=>setPhoneOpen(false)}>Cancelar</button>
     <button type="submit" className="vf-btn is-small is-primary" disabled={phoneBusy||!phoneOk||!phoneValue.trim()}>{phoneBusy?"Salvando…":"Salvar celular"}</button></div>
   </form>}
   {phoneMsg&&<div className={"vf-toast"+(phoneMsg.startsWith("✓")?"":" is-error")} role="status">{phoneMsg.replace(/^✓ /,"")}</div>}
   <p className="vf-note">Participando desde {day(profile.joined_at)} · aceite pelo {profile.consent_channel==="customer_portal"?"portal do participante":"formulário da loja"}.</p>
   {profile.balance_status==="ledger_only"&&profile.cashback_balance_cents!==null&&<details className="vf-sale-more vf-wallet-technical">
    <summary>Registros internos de teste</summary>
    <p className="vf-muted vf-small">Resgate desativado. Este registro em reais é só para verificação interna; não são pontos nem benefício disponível.</p>
    {!wallet&&<button type="button" className="vf-btn is-small vf-wallet-open" disabled={walletState==="loading"} onClick={()=>void openWallet(profile)}>
     {walletState==="loading"?"Carregando…":"Ver extrato técnico"}</button>}
    {walletState==="error"&&<p role="alert" className="vf-toast is-error">Falha ao consultar extrato.</p>}
    {wallet?.balances&&<><div className="vf-grid3">
      <div className="vf-kpi"><span className="vf-kpi-label">Disponível</span><strong>{money(wallet.balances.available_cents)}</strong></div>
      <div className="vf-kpi"><span className="vf-kpi-label">Pendente</span><strong>{money(wallet.balances.pending_cents)}</strong></div>
      <div className="vf-kpi"><span className="vf-kpi-label">Reservado</span><strong>{money(wallet.balances.reserved_cents)}</strong></div></div>
     {wallet.events.length?<ul className="vf-list">{wallet.events.map(ev=><li key={ev.id} className="vf-row">
      <span className="vf-row-main"><strong>{movements[ev.kind]}</strong><span>{day(ev.created_at)} · regra {ev.rule_version}</span></span>
      <strong className="vf-num">{money(ev.amount_cents)}</strong></li>)}</ul>:<p className="vf-muted vf-small">Nenhuma movimentação registrada.</p>}</>}
    {wallet&&!wallet.balances&&<p className="vf-muted vf-small">Carteira ainda não disponível para este participante.</p>}
   </details>}
  </section>}
 </section>;
}
