import {useEffect,useMemo,useRef,useState,type FormEvent} from "react";
import {Check,CheckCircle2,Clock3,Link2,RefreshCw,Search,Smartphone,UserRound,X} from "lucide-react";
import {ApiError,merchantApi,type ManualSaleRecord,type PointRuleDraft,
 type ProgramParticipant,type Store} from "./api";
import {pointValueText,summarizeClub} from "./club-summary";
import {initialsOf} from "./ActionCenter";
import PaidOrderCheck from "./PaidOrderCheck";
import NuvemshopOrdersFeed from "./NuvemshopOrdersFeed";
import "./vf-ui.css";
import "./sales-workspace.css";

/* Vendas — réplica do protótipo aprovado: "Venda em 10 segundos".
   Esquerda: cliente, valor (com atalhos) e registrar. Direita: quanto o cliente
   vai receber pela regra do clube e as vendas para conferir. Abaixo: pedidos da
   Nuvemshop e o histórico do balcão. Registrar e conferir não creditam pontos. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const localNow=()=>new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
export const centsFromText=(raw:string):number|null=>{
 const clean=raw.trim().replace(/^R\$\s*/i,"").replace(/\.(?=\d{3}(\D|$))/g,"");
 if(!/^\d{1,7}(?:[,.]\d{1,2})?$/.test(clean))return null;
 const [whole,decimal=""]=clean.replace(",",".").split(".");
 const value=Number(whole)*100+Number(decimal.padEnd(2,"0"));
 return Number.isSafeInteger(value)&&value>0&&value<=100_000_000?value:null;
};
export const receiptReference=(raw:string):string|null=>{
 const value=raw.normalize("NFKC").trim().toUpperCase().replace(/\s+/g,"-");
 const reference=/^\d{1,72}$/.test(value)?"CUPOM-"+value:value;
 return /^[A-Z0-9][A-Z0-9._/-]{3,79}$/.test(reference)?reference:null;
};
export const phoneDigits=(raw:string)=>raw.replace(/\D/g,"").replace(/^55(?=\d{10,11}$)/,"");
const formatPhone=(raw:string)=>{
 if(raw.trim().startsWith("+"))return raw.slice(0,20);
 const d=raw.replace(/\D/g,"").slice(0,11);
 if(d.length<=2)return d.length?"("+d:"";
 if(d.length<=6)return `(${d.slice(0,2)}) ${d.slice(2)}`;
 if(d.length<=10)return `(${d.slice(0,2)}) ${d.slice(2,6)}-${d.slice(6)}`;
 return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`;
};
const when=(iso:string)=>{
 const d=new Date(iso);if(Number.isNaN(d.getTime()))return "";
 const today=new Date();const same=d.toDateString()===today.toDateString();
 return (same?"hoje ":d.toLocaleDateString("pt-BR",{day:"2-digit",month:"short"})+" ")+d.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
};
const stateChip:Record<ManualSaleRecord["state"],[string,string]>={
 awaiting_member:["Sem cliente","is-soft"],
 awaiting_review:["Aguardando conferência","is-gold"],
 verified_manual:["Conferida","is-ok"],
 rejected:["Rejeitada","is-danger"],
};
const TONES=["tone-1","tone-2","tone-3","tone-4","tone-5"];
const QUICK=[5000,10000,20000];

export default function SalesWorkspace({tenantId,role}:{tenantId:string;role:Store["role"]}){
 const canEdit=role==="owner"||role==="admin";
 const [items,setItems]=useState<ManualSaleRecord[]>([]);
 const [loading,setLoading]=useState(true);
 const [listError,setListError]=useState("");
 const [version,setVersion]=useState(0);
 const [rule,setRule]=useState<PointRuleDraft|null>(null);
 const [pointValue,setPointValue]=useState<number|null>(null);

 const [amount,setAmount]=useState("");
 const [receipt,setReceipt]=useState("");
 const [customTime,setCustomTime]=useState(false);
 const [paidAt,setPaidAt]=useState(localNow);
 const [query,setQuery]=useState("");
 const [people,setPeople]=useState<ProgramParticipant[]>([]);
 const [peopleError,setPeopleError]=useState(false);
 type Person={id:string;display_name:string;detail:string};
 const [chosen,setChosen]=useState<Person|null|undefined>(undefined); // undefined = não escolhido; null = fora do clube
 const [mode,setMode]=useState<"phone"|"name">("phone");
 const [phone,setPhone]=useState("");
 const [phoneState,setPhoneState]=useState<"idle"|"looking"|"error">("idle");
 const [phoneError,setPhoneError]=useState("");
 const resetClient=()=>{setChosen(undefined);setPhone("");setQuery("");setPhoneState("idle");};
 const [busy,setBusy]=useState(false);
 const [formError,setFormError]=useState("");
 const [toast,setToast]=useState("");

 const [bottom,setBottom]=useState<"history"|"online">("history");
 const [reviewing,setReviewing]=useState<string|null>(null);
 const [reviewWhere,setReviewWhere]=useState<"side"|"list">("side");
 const [note,setNote]=useState("");
 const [reviewMsg,setReviewMsg]=useState("");
 const [reviewError,setReviewError]=useState("");
 const [linking,setLinking]=useState<string|null>(null);
 const [linkTarget,setLinkTarget]=useState("");
 const amountRef=useRef<HTMLInputElement>(null);

 useEffect(()=>{
  let active=true;setLoading(true);setListError("");
  merchantApi.listManualSales(tenantId).then(d=>{if(active)setItems(d.items);})
   .catch(e=>{if(active)setListError(e instanceof ApiError?e.message:"Não foi possível consultar as vendas.");})
   .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId,version]);

 useEffect(()=>{
  if(!canEdit)return;
  let active=true;
  Promise.allSettled([merchantApi.getPointRuleDraft(tenantId),merchantApi.listDiscountRewardDrafts(tenantId)]).then(([r,w])=>{
   if(!active)return;
   const nextRule=r.status==="fulfilled"?r.value.rule:null;
   setRule(nextRule);
   const s=summarizeClub(nextRule,w.status==="fulfilled"?w.value.items:[]);
   setPointValue(s.pointValue&&s.pointValue.min===s.pointValue.max?s.pointValue.max:null);
  });
  return()=>{active=false};
 },[tenantId,canEdit]);

 useEffect(()=>{
  if(!canEdit)return;
  let active=true;setPeopleError(false);
  const timer=window.setTimeout(()=>{
   merchantApi.listParticipants(tenantId,{status:"active",q:query.trim(),offset:0})
    .then(d=>{if(active)setPeople(d.items);})
    .catch(()=>{if(active){setPeople([]);setPeopleError(true);}});
  },query?250:0);
  return()=>{active=false;window.clearTimeout(timer)};
 },[tenantId,query,canEdit]);

 useEffect(()=>{
  if(!canEdit||mode!=="phone"||chosen!==undefined)return;
  const digits=phoneDigits(phone);
  if(digits.length<10){setPhoneState("idle");return;}
  let active=true;setPhoneState("looking");
  const timer=window.setTimeout(()=>{
   merchantApi.findParticipantByPhone(tenantId,phone).then(r=>{
    if(!active)return;setPhoneState("idle");
    setChosen(r.match?{id:r.match.id,display_name:r.match.display_name,
     detail:"Celular final "+(r.match.phone_last4??digits.slice(-4))}:null);
   }).catch(e=>{if(active){setPhoneState("error");setPhoneError(e instanceof ApiError?e.message:"Não foi possível consultar o celular.");}});
  },350);
  return()=>{active=false;window.clearTimeout(timer)};
 },[tenantId,phone,mode,chosen,canEdit]);

 const cents=centsFromText(amount);
 const preview=useMemo(()=>{
  if(!rule||cents===null)return null;
  const points=Math.floor(cents*rule.points/rule.per_cents);
  return {points,value:pointValue===null?null:money(Math.round(points*pointValue/100))};
 },[rule,cents,pointValue]);
 const holdText=!rule?"":rule.hold_days===0?"Liberam logo após a conferência.":`Liberam ${rule.hold_days} dia${rule.hold_days===1?"":"s"} depois da conferência.`;

 const pending=items.filter(i=>i.state==="awaiting_review");

 const submit=async(event:FormEvent)=>{
  event.preventDefault();
  if(busy||!canEdit)return;
  setFormError("");setToast("");
  if(chosen===undefined){setFormError("Escolha o cliente ou marque que ele ainda não participa do clube.");return;}
  if(cents===null){setFormError("Confira o valor da compra. Ex.: 89,90");amountRef.current?.focus();return;}
  const reference=receiptReference(receipt);
  if(!reference){setFormError(receipt.trim()?"O número do cupom tem caracteres inválidos. Use letras, números, ponto ou traço."
   :"Informe o número do cupom ou recibo para conferir depois.");return;}
  const time=customTime?new Date(paidAt):new Date();
  if(Number.isNaN(time.getTime())){setFormError("Informe uma data de venda válida.");return;}
  setBusy(true);
  try{
   const keepPhone=!chosen&&mode==="phone"&&phoneDigits(phone).length>=10;
   const result=await merchantApi.createManualSale(tenantId,{reference,eligible_amount_cents:cents,
    participant_id:chosen?chosen.id:null,reported_paid_at:time.toISOString(),evidence_reference:reference,
    ...(keepPhone?{customer_phone:phone}:{})});
   setToast(result.already_recorded?"Este cupom já estava registrado. Nada foi duplicado."
    :chosen?"Venda registrada. Os pontos ficam pendentes até a conferência."
    :keepPhone?"Venda guardada com o celular do cliente. Vincule quando ele entrar no clube."
    :"Venda registrada sem cliente. Ela não gera pontos até alguém do clube ser vinculado.");
   setAmount("");setReceipt("");resetClient();setCustomTime(false);setPaidAt(localNow());
   setVersion(v=>v+1);
  }catch(e){setFormError(e instanceof ApiError?e.message:"Não foi possível registrar a venda.");}
  finally{setBusy(false);}
 };

 const review=async(sale:ManualSaleRecord,decision:"approve"|"reject")=>{
  if(busy)return;setBusy(true);setReviewError("");setReviewMsg("");
  try{
   const r=await merchantApi.reviewManualSale(tenantId,sale.id,decision,note);
   setReviewMsg(decision==="reject"?"Venda rejeitada. Nenhum ponto foi creditado."
    :r.review_mode==="self_review"?"Conferência do responsável registrada e auditada. Nenhum ponto foi creditado."
    :"Conferência registrada. Nenhum ponto foi creditado.");
   setReviewing(null);setNote("");setVersion(v=>v+1);
  }catch(e){setReviewError(e instanceof ApiError?e.message:"Não foi possível concluir a conferência.");}
  finally{setBusy(false);}
 };
 const link=async(sale:ManualSaleRecord,target=linkTarget)=>{
  if(busy||!target)return;setBusy(true);setReviewError("");setReviewMsg("");
  try{
   await merchantApi.linkManualSale(tenantId,sale.id,target);
   setReviewMsg("Cliente vinculado à venda. Agora ela pode ser conferida.");
   setLinking(null);setLinkTarget("");setVersion(v=>v+1);
  }catch(e){setReviewError(e instanceof ApiError?e.message:"É preciso um participante com contato confirmado para vincular.");}
  finally{setBusy(false);}
 };

 const reviewPanel=(sale:ManualSaleRecord)=><div className="vf-sale-review" aria-label="Conferir venda">
  <p className="vf-small">Confira o cupom <strong>{sale.evidence_reference}</strong> de <strong>{money(sale.eligible_amount_cents)}</strong> antes de concluir.</p>
  {sale.submitted_by_me&&<p className="vf-note">Você está conferindo o próprio lançamento como responsável. A justificativa fica registrada na auditoria.</p>}
  <label className="vf-field is-compact">Como você conferiu?
   <textarea value={note} onChange={e=>setNote(e.target.value)} rows={2} minLength={10} maxLength={240}
    placeholder="Ex.: Cupom e pagamento conferidos no caixa."/>
  </label>
  <div className="vf-sale-review-actions">
   <button type="button" className="vf-btn is-small" onClick={()=>{setReviewing(null);setNote("");}}>Cancelar</button>
   <button type="button" className="vf-btn is-small is-danger" disabled={busy||note.trim().length<10} onClick={()=>void review(sale,"reject")}>Rejeitar</button>
   <button type="button" className="vf-btn is-small is-primary" disabled={busy||note.trim().length<10} onClick={()=>void review(sale,"approve")}><Check size={16}/> Confirmar conferência</button>
  </div>
 </div>;

 return <section className="vf-screen vf-sales-page" aria-labelledby="vf-sales-title">
  <div className="vf-head"><div><span className="vf-eyebrow">Vendas</span><h1 id="vf-sales-title" className="vf-h1">Venda em 10 segundos</h1></div></div>

  {canEdit?<div className="vf-grid2">
   <form className="vf-card vf-sale-form" onSubmit={submit} noValidate aria-label="Registrar venda no balcão">
    <div className="vf-field">
     <span id="vf-sale-client-label">{mode==="phone"?"Celular do cliente":"Cliente"}</span>
     {chosen?<div className="vf-sale-chosen">
       <span className="vf-avatar tone-1" aria-hidden="true">{initialsOf(chosen.display_name)}</span>
       <div className="vf-row-main"><strong>{chosen.display_name}</strong><span>{chosen.detail}</span></div>
       <button type="button" className="vf-btn is-small" onClick={resetClient}>Trocar</button>
      </div>
     :chosen===null?<div className="vf-sale-chosen is-outside">
       <span className="vf-ico tone-gold" aria-hidden="true"><UserRound size={18}/></span>
       <div className="vf-row-main"><strong>{phoneDigits(phone).length>=10&&mode==="phone"?"Celular ainda não está no clube":"Cliente ainda não participa"}</strong>
        <span>{phoneDigits(phone).length>=10&&mode==="phone"
         ?"A venda fica guardada com este celular. Quando a pessoa entrar no clube com o mesmo número, é só vincular."
         :"A venda fica registrada sem pontos."}</span></div>
       <button type="button" className="vf-btn is-small" onClick={resetClient}>Trocar</button>
      </div>
     :mode==="phone"?<>
       <div className="vf-sale-search">
        <Smartphone size={18} aria-hidden="true"/>
        <input id="vf-sale-phone" type="tel" inputMode="tel" aria-labelledby="vf-sale-client-label" autoComplete="off" maxLength={20}
         placeholder="(31) 99999-9999" value={phone} onChange={e=>setPhone(formatPhone(e.target.value))}/>
       </div>
       <small role="status">{phoneState==="looking"?"Procurando no clube…":phoneState==="error"?phoneError
        :"Digite o celular com DDD. O sistema encontra o cliente sozinho."}</small>
       <div className="vf-sale-client-alt">
        <button type="button" className="vf-btn is-link" onClick={()=>{setMode("name");setFormError("");}}>Buscar pelo nome</button>
        <button type="button" className="vf-btn is-link vf-sale-outside" onClick={()=>{setChosen(null);setPhone("");setFormError("");}}>Cliente ainda não participa do clube</button>
       </div>
      </>
     :<>
       <div className="vf-sale-search">
        <Search size={18} aria-hidden="true"/>
        <input id="vf-sale-client" type="search" aria-labelledby="vf-sale-client-label" autoComplete="off" maxLength={80}
         placeholder="Buscar por nome ou e-mail" value={query} onChange={e=>setQuery(e.target.value)}/>
       </div>
       {query.trim()?<ul className="vf-sale-people" aria-label="Participantes encontrados">
        {people.slice(0,5).map((p,i)=><li key={p.id}><button type="button" onClick={()=>{setChosen({id:p.id,display_name:p.display_name,detail:p.contact_email});setFormError("");}}>
         <span className={"vf-avatar "+TONES[i%5]} aria-hidden="true">{initialsOf(p.display_name)}</span>
         <span className="vf-row-main"><strong>{p.display_name}</strong><span>{p.contact_email}</span></span></button></li>)}
        {!peopleError&&people.length===0&&<li className="vf-sale-people-empty">Ninguém encontrado com essa busca.</li>}
        {peopleError&&<li className="vf-sale-people-empty">Não foi possível carregar os participantes.</li>}
       </ul>:<small>Digite parte do nome ou do e-mail do cliente.</small>}
       <div className="vf-sale-client-alt">
        <button type="button" className="vf-btn is-link" onClick={()=>{setMode("phone");setQuery("");setFormError("");}}>Usar o celular</button>
        <button type="button" className="vf-btn is-link vf-sale-outside" onClick={()=>{setChosen(null);setFormError("");}}>Cliente ainda não participa do clube</button>
       </div>
      </>}
    </div>

    <label className="vf-field" htmlFor="vf-sale-amount">Valor da compra (R$)
     <input id="vf-sale-amount" ref={amountRef} inputMode="decimal" autoComplete="off" maxLength={12} placeholder="0,00"
      value={amount} onChange={e=>setAmount(e.target.value)}/>
    </label>
    <div className="vf-pills" role="group" aria-label="Valores rápidos">
     {QUICK.map(v=><button key={v} type="button" className={"vf-pill"+(cents===v?" is-on":"")} aria-pressed={cents===v}
      onClick={()=>setAmount((v/100).toFixed(2).replace(".",","))}>{money(v).replace(",00","")}</button>)}
    </div>

    <label className="vf-field is-compact" htmlFor="vf-sale-receipt">Número do cupom ou recibo
     <input id="vf-sale-receipt" maxLength={80} autoComplete="off" placeholder="Ex.: 0042" value={receipt} onChange={e=>setReceipt(e.target.value)}/>
     <small>É o que você confere depois e evita registrar a mesma venda duas vezes.</small>
    </label>
    <details className="vf-sale-more" open={customTime}>
     <summary>Outra data</summary>
     <button type="button" className="vf-btn is-link" aria-expanded={customTime} onClick={()=>{setCustomTime(v=>!v);setPaidAt(localNow());}}>
      <Clock3 size={15}/> A compra foi em outra data?</button>
     {customTime&&<label className="vf-field is-compact" htmlFor="vf-sale-date">Data e hora da venda
      <input id="vf-sale-date" type="datetime-local" value={paidAt} onChange={e=>setPaidAt(e.target.value)}/></label>}
    </details>

    {formError&&<div className="vf-toast is-error" role="alert"><X size={18}/>{formError}</div>}
    <button type="submit" className="vf-btn is-primary is-big" disabled={busy}>{busy?"Registrando…":"Registrar venda"}</button>
    {toast&&<div className="vf-toast" role="status"><Check size={18}/>{toast}</div>}
   </form>

   <section className="vf-card is-soft vf-sale-side" aria-labelledby="vf-sale-gain">
    <span id="vf-sale-gain" className="vf-eyebrow">O cliente vai receber</span>
    {preview?<><strong className="vf-sale-points">{`${preview.points.toLocaleString("pt-BR")} ponto${preview.points===1?"":"s"}`}</strong>
     {preview.value&&<span className="vf-sale-value">= {preview.value} em desconto</span>}</>
     :<span className="vf-sale-value is-hint">{!rule?"Defina a regra de pontos em Meu clube para ver a prévia.":"Digite o valor da compra para ver os pontos."}</span>}
    {rule&&<span className="vf-muted vf-small">{holdText} Se a compra for cancelada, os pontos saem antes do uso.{pointValue!==null?` Cada ponto vale ${pointValueText(pointValue)}.`:""}</span>}

    <div className="vf-sale-review-box">
     <strong className="vf-h3">Para conferir</strong>
     {reviewMsg&&<div className="vf-toast" role="status"><CheckCircle2 size={18}/>{reviewMsg}</div>}
     {reviewError&&<div className="vf-toast is-error" role="alert"><X size={18}/>{reviewError}</div>}
     {loading?<p className="vf-muted vf-small" role="status">Carregando vendas…</p>
      :pending.length===0?<p className="vf-muted vf-small">Nenhuma venda aguardando conferência.</p>
      :<ul className="vf-list">{pending.map((sale,i)=><li key={sale.id} className="vf-sale-pending">
        <div className="vf-row">
         <span className={"vf-avatar "+TONES[(i+2)%5]} aria-hidden="true">{initialsOf(sale.participant_name)}</span>
         <div className="vf-row-main"><strong>{sale.participant_name||"Cliente"}</strong><span>{money(sale.eligible_amount_cents)} · {when(sale.reported_paid_at)}</span></div>
         {!(reviewing===sale.id&&reviewWhere==="side")&&<button type="button" className="vf-btn is-small" onClick={()=>{setReviewing(sale.id);setReviewWhere("side");setNote("");setReviewMsg("");}}>Conferir</button>}
        </div>
        {reviewing===sale.id&&reviewWhere==="side"&&reviewPanel(sale)}
       </li>)}</ul>}
    </div>
   </section>
  </div>
  :<section className="vf-card"><h2 className="vf-h2">Registro disponível para administradores</h2>
   <p className="vf-lead">Esta conta acompanha as vendas, mas não registra nem confere.</p></section>}

  <div className="vf-tabs vf-sale-bottom-tabs" role="tablist" aria-label="Histórico e loja online">
   <button type="button" role="tab" aria-selected={bottom==="history"} className={"vf-tab"+(bottom==="history"?" is-on":"")} onClick={()=>setBottom("history")}>Histórico do balcão</button>
   <button type="button" role="tab" aria-selected={bottom==="online"} className={"vf-tab"+(bottom==="online"?" is-on":"")} onClick={()=>setBottom("online")}>Pedidos da Nuvemshop</button>
  </div>
  {bottom==="online"&&<section className="vf-card vf-sale-online" aria-labelledby="vf-sales-online-title">
   <div className="vf-card-head"><div><h2 id="vf-sales-online-title" className="vf-h2">Pedidos da Nuvemshop</h2>
    <span className="vf-muted vf-small">Compras do site não precisam ser registradas aqui. Esta lista só lê a loja.</span></div></div>
   <NuvemshopOrdersFeed tenantId={tenantId}/>
   <details className="vf-sale-more"><summary>Consultar um pedido pelo número ou link</summary><PaidOrderCheck tenantId={tenantId}/></details>
  </section>}
  {bottom==="history"&&<section className="vf-card" aria-labelledby="vf-sale-history-title">
   <div className="vf-card-head"><div><h2 id="vf-sale-history-title" className="vf-h2">Vendas do balcão</h2>
    <span className="vf-muted vf-small">{pending.length?`${pending.length} aguardando conferência.`:"Histórico das vendas registradas na loja física."}</span></div>
    <button type="button" className="vf-btn is-small" onClick={()=>setVersion(v=>v+1)}><RefreshCw size={16}/> Atualizar</button></div>
   {listError&&<div className="vf-toast is-error" role="alert">{listError}</div>}
   {loading?<p className="vf-muted" role="status">Carregando vendas…</p>
    :items.length===0?<div className="vf-empty"><p>Nenhuma venda registrada ainda. As vendas do balcão aparecem aqui.</p></div>
    :<ul className="vf-list">{items.map(sale=>{const [label,chip]=stateChip[sale.state];return <li key={sale.id} className="vf-sale-record">
      <div className="vf-row is-wrap">
       <div className="vf-row-main"><strong>{sale.participant_name||"Cliente fora do clube"}</strong>
        <span>{sale.reference} · {when(sale.reported_paid_at)}</span></div>
       <strong className="vf-num">{money(sale.eligible_amount_cents)}</strong>
       <span className={"vf-chip vf-sale-state "+chip}>{label}</span>
       {canEdit&&sale.state==="awaiting_member"&&sale.suggested_participant&&linking!==sale.id&&
        <button type="button" className="vf-btn is-small is-primary" disabled={busy} onClick={()=>void link(sale,sale.suggested_participant!.id)}>
         <Link2 size={15}/> Vincular a {sale.suggested_participant.display_name}</button>}
       {canEdit&&sale.state==="awaiting_member"&&!sale.suggested_participant&&linking!==sale.id&&<button type="button" className="vf-btn is-small" onClick={()=>{setLinking(sale.id);setLinkTarget("");}}>Vincular cliente</button>}
       {canEdit&&sale.state==="awaiting_review"&&!(reviewing===sale.id&&reviewWhere==="list")&&<button type="button" className="vf-btn is-small" onClick={()=>{setReviewing(sale.id);setReviewWhere("list");setNote("");setReviewMsg("");}}>Conferir venda</button>}
      </div>
      {reviewing===sale.id&&reviewWhere==="list"&&reviewPanel(sale)}
      {linking===sale.id&&<div className="vf-sale-review" aria-label="Vincular cliente à venda">
       <label className="vf-field is-compact">Participante com contato confirmado
        <select value={linkTarget} onChange={e=>setLinkTarget(e.target.value)}>
         <option value="" disabled>Selecione o participante</option>
         {people.map(p=><option key={p.id} value={p.id}>{p.display_name} · {p.contact_email}</option>)}
        </select></label>
       <div className="vf-sale-review-actions">
        <button type="button" className="vf-btn is-small" onClick={()=>setLinking(null)}>Cancelar</button>
        <button type="button" className="vf-btn is-small is-primary" disabled={busy||!linkTarget} onClick={()=>void link(sale)}>Vincular</button>
       </div>
      </div>}
     </li>;})}</ul>}
  </section>}
 </section>;
}
