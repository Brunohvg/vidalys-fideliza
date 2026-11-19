import {useEffect,useMemo,useRef,useState,type FormEvent} from "react";
import {Check,CheckCircle2,Clock3,Gift,Link2,RefreshCw,Search,ShoppingBag,Smartphone,Star,Store as StoreIcon,
 TriangleAlert,Undo2,UserRound,X} from "lucide-react";
import {ApiError,merchantApi,type CounterWallet,type ProgramInfo,type ManualSaleRecord,type PaidOrderInspection,type PointRuleDraft,
 type ProgramParticipant,type Store} from "./api";
import {pointValueText,summarizeClub} from "./club-summary";
import {initialsOf} from "./ActionCenter";
import PaidOrderCheck from "./PaidOrderCheck";
import {formatPhone,phoneComplete,phoneDigits} from "./phone-mask";
export {phoneDigits};
import "./vf-ui.css";
import "./sales-workspace.css";

/* Vendas em 3 abas, cada uma para um trabalho:
   Balcão  — o vendedor com a cliente na frente: achar, usar vale, registrar, desfazer.
   Conferir — dono/admin aprova o que foi lançado (com o clube ativo, aprovar gera o saldo).
   Pedidos — consulta: balcão e site numa lista só. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const pts=(n:number)=>n.toLocaleString("pt-BR");
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
const NO_RECEIPT="SEM-CUPOM-";
const autoReference=()=>NO_RECEIPT+Date.now().toString(36).toUpperCase()+"-"+Math.random().toString(36).slice(2,6).toUpperCase();
const receiptLabel=(ref:string)=>ref.startsWith(NO_RECEIPT)?"sem cupom":ref;
const when=(iso:string|null)=>{
 if(!iso)return "";
 const d=new Date(iso);if(Number.isNaN(d.getTime()))return "";
 const same=d.toDateString()===new Date().toDateString();
 return (same?"hoje ":d.toLocaleDateString("pt-BR",{day:"2-digit",month:"short"})+" ")+d.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
};
const dayMonth=(d:Date)=>d.toLocaleDateString("pt-BR",{day:"2-digit",month:"short"});
/* Ganho por venda: pontos, ou reais no modo giftback (1 unidade = R$ 0,01). */
const gain=(n:number,gift:boolean)=>gift?money(n):pts(n)+" pts";
const firstName=(name:string)=>name.trim().split(/\s+/)[0]||name;
const isToday=(iso:string)=>new Date(iso).toDateString()===new Date().toDateString();
const TONES=["tone-1","tone-2","tone-3","tone-4","tone-5"];
const COUNTER_STATE:Record<ManualSaleRecord["state"],[string,string]>={
 awaiting_member:["Sem cliente","is-soft"],awaiting_review:["Aguardando conferência","is-gold"],
 verified_manual:["Conferida","is-ok"],rejected:["Recusada","is-danger"],
};

export type SaleClient={id:string;display_name:string;detail:string};
type Tab="counter"|"review"|"orders";
type Shared={tenantId:string;items:ManualSaleRecord[];loading:boolean;listError:string;pilot:boolean;avgTicket:number;program:ProgramInfo;
 rule:PointRuleDraft|null;pointValue:number|null;reload:()=>void};

export default function SalesWorkspace({tenantId,role,initialClient}:{tenantId:string;role:Store["role"];initialClient?:SaleClient|null}){
 const canEdit=role==="owner"||role==="admin";
 const [tab,setTab]=useState<Tab>(canEdit?"counter":"orders");
 const [items,setItems]=useState<ManualSaleRecord[]>([]);
 const [pilot,setPilot]=useState(false);
 const [avgTicket,setAvgTicket]=useState(0);
 const [program,setProgram]=useState<ProgramInfo>({mode:"points"});
 const [loading,setLoading]=useState(true);
 const [listError,setListError]=useState("");
 const [version,setVersion]=useState(0);
 const [rule,setRule]=useState<PointRuleDraft|null>(null);
 const [pointValue,setPointValue]=useState<number|null>(null);

 useEffect(()=>{
  let active=true;setLoading(true);setListError("");
  merchantApi.listManualSales(tenantId).then(d=>{if(active){setItems(d.items);setPilot(Boolean(d.pilot_active));setAvgTicket(d.average_ticket_cents||0);setProgram(d.program&&d.program.mode?d.program:{mode:"points"});}})
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

 const pending=items.filter(i=>i.state==="awaiting_review"||i.state==="awaiting_member").length;
 const shared:Shared={tenantId,items,loading,listError,pilot,avgTicket,program,rule,pointValue,reload:()=>setVersion(v=>v+1)};
 const TABS:[Tab,string][]=canEdit?[["counter","Balcão"],["review","Conferir"],["orders","Pedidos"]]:[["orders","Pedidos"]];

 return <section className="vf-screen vf-sales-page" aria-labelledby="vf-sales-title">
  <div className="vf-head"><div><span className="vf-eyebrow">Vendas</span><h1 id="vf-sales-title" className="vf-h1">Vendas</h1></div></div>
  <div className="vs-tabs" role="tablist" aria-label="Áreas de vendas">
   {TABS.map(([key,label])=><button key={key} type="button" role="tab" id={"vs-tab-"+key} aria-controls={"vs-panel-"+key}
    aria-selected={tab===key} className={"vs-tab"+(tab===key?" is-on":"")} onClick={()=>setTab(key)}>
    {label}{key==="review"&&pending>0&&<span className="vs-tab-count" aria-label={pending+" para conferir"}>{pending}</span>}</button>)}
  </div>
  <div role="tabpanel" id={"vs-panel-"+tab} aria-labelledby={"vs-tab-"+tab} className="vs-panel">
   {tab==="counter"&&<Counter shared={shared} initialClient={initialClient}/>}
   {tab==="review"&&<Review shared={shared}/>}
   {tab==="orders"&&<Orders shared={shared}/>}
  </div>
 </section>;
}

/* ---------------- Balcão ---------------- */

type Person={id:string;display_name:string;detail:string};

function Counter({shared,initialClient}:{shared:Shared;initialClient?:SaleClient|null}){
 const {tenantId,items,pilot,avgTicket,program,rule,pointValue,reload}=shared;
 const gift=program.mode==="giftback"?program:null;
 const [useCredit,setUseCredit]=useState(false);
 const [amount,setAmount]=useState("");
 const [receipt,setReceipt]=useState("");
 const [more,setMore]=useState(false);
 const [customTime,setCustomTime]=useState(false);
 const [paidAt,setPaidAt]=useState(localNow);
 const [query,setQuery]=useState("");
 const [people,setPeople]=useState<ProgramParticipant[]>([]);
 const [peopleError,setPeopleError]=useState(false);
 const [chosen,setChosen]=useState<Person|null|undefined>(initialClient??undefined); // undefined = não escolhido; null = fora do clube
 const [mode,setMode]=useState<"phone"|"name">("phone");
 const [phone,setPhone]=useState("");
 const [phoneState,setPhoneState]=useState<"idle"|"looking"|"error">("idle");
 const [phoneError,setPhoneError]=useState("");
 const [wallet,setWallet]=useState<CounterWallet|null>(null);
 const [rewardId,setRewardId]=useState("");
 const [busy,setBusy]=useState(false);
 const [formError,setFormError]=useState("");
 const [toast,setToast]=useState("");
 const [undoMsg,setUndoMsg]=useState("");
 const amountRef=useRef<HTMLInputElement>(null);
 const [pendingPhone,setPendingPhone]=useState("");
 const [phoneSaved,setPhoneSaved]=useState("");
 const resetClient=()=>{setChosen(undefined);setPhone("");setQuery("");setPhoneState("idle");setWallet(null);setRewardId("");setPendingPhone("");setPhoneSaved("");};

 useEffect(()=>{
  let active=true;setPeopleError(false);
  const timer=window.setTimeout(()=>{
   merchantApi.listParticipants(tenantId,{status:"active",q:query.trim(),offset:0})
    .then(d=>{if(active)setPeople(d.items);})
    .catch(()=>{if(active){setPeople([]);setPeopleError(true);}});
  },query?250:0);
  return()=>{active=false;window.clearTimeout(timer)};
 },[tenantId,query]);

 useEffect(()=>{
  if(mode!=="phone"||chosen!==undefined)return;
  const digits=phoneDigits(phone);
  if(!phoneComplete(phone)){setPhoneState("idle");return;}
  let active=true;setPhoneState("looking");
  const timer=window.setTimeout(()=>{
   merchantApi.findParticipantByPhone(tenantId,phone).then(r=>{
    if(!active)return;setPhoneState("idle");
    setChosen(r.match?{id:r.match.id,display_name:r.match.display_name,
     detail:"Celular final "+(r.match.phone_last4??digits.slice(-4))}:null);
   }).catch(e=>{if(active){setPhoneState("error");setPhoneError(e instanceof ApiError?e.message:"Não foi possível consultar o celular.");}});
  },350);
  return()=>{active=false;window.clearTimeout(timer)};
 },[tenantId,phone,mode,chosen]);

 useEffect(()=>{
  setWallet(null);setRewardId("");setUseCredit(false);
  if(!chosen)return;
  let active=true;
  merchantApi.counterWallet(tenantId,chosen.id).then(w=>{
   if(active)setWallet(w&&Array.isArray(w.rewards)&&typeof w.available==="number"&&typeof w.pending==="number"?w:null);}).catch(()=>{if(active)setWallet(null);});
  return()=>{active=false};
 },[tenantId,chosen]);

 const cents=centsFromText(amount);
 const reward=gift?null:wallet?.rewards.find(r=>r.id===rewardId)||null;
 const credit=gift&&wallet?.credit?wallet.credit.available_cents:0;
 const creditOn=Boolean(gift&&useCredit&&credit>0);
 const discount=reward?reward.discount_cents:creditOn?credit:0;
 const paid=cents!==null?Math.max(cents-discount,0):null;
 const points=useMemo(()=>paid===null?null:gift?Math.min(Math.floor(paid*gift.percent_bps/10000),gift.cap_cents)
  :rule?Math.floor(paid*rule.points/rule.per_cents):null,[rule,paid,gift]);
 const rewardProblem=reward&&cents!==null?(cents<reward.min_order_cents?`Este vale pede compra mínima de ${money(reward.min_order_cents)}.`
  :reward.discount_cents>=cents?"O vale não pode ser maior que a compra.":"")
  :creditOn&&gift&&cents!==null?(cents<gift.min_order_cents?`O crédito vale em compras a partir de ${money(gift.min_order_cents)}.`
  :credit>=cents?"O crédito não pode ser maior que a compra.":""):"";
 const usable=(wallet?.rewards||[]).filter(r=>r.affordable);
 const mine=items.filter(i=>i.submitted_by_me&&isToday(i.created_at)).slice(0,8);

 // Próxima meta depois desta compra (pontos ainda em carência contam para a conta).
 const projected=!gift&&wallet&&points!==null?wallet.available-(reward?.points_cost||0)+wallet.pending+points:null;
 const goal=wallet&&projected!==null?wallet.rewards.filter(r=>!r.exhausted&&r.points_cost>projected).sort((a,b)=>a.points_cost-b.points_cost)[0]:null;
 const missingCents=goal&&projected!==null&&rule?Math.ceil((goal.points_cost-projected)*rule.per_cents/rule.points):null;
 // A dica só aparece quando a meta está perto (até 3 compras médias; sem histórico, até R$ 300).
 const nearLimit=avgTicket>0?avgTicket*3:30000;
 const showTip=missingCents!==null&&missingCents<=nearLimit;
 const holdDays=gift?gift.hold_days:rule?rule.hold_days:0;
 const releaseDate=dayMonth(new Date(Date.now()+holdDays*86400000));

 const submit=async(event:FormEvent)=>{
  event.preventDefault();
  if(busy)return;
  setFormError("");setToast("");setUndoMsg("");
  if(chosen===undefined){setFormError("Escolha o cliente ou marque que ele ainda não participa do clube.");return;}
  if(cents===null){setFormError("Confira o valor da compra. Ex.: 89,90");amountRef.current?.focus();return;}
  if(rewardProblem){setFormError(rewardProblem);return;}
  let reference:string|null=autoReference();
  if(receipt.trim()){
   reference=receiptReference(receipt);
   if(!reference){setFormError("O número do cupom tem caracteres inválidos. Use letras, números, ponto ou traço.");setMore(true);return;}
  }
  const time=customTime?new Date(paidAt):new Date();
  if(Number.isNaN(time.getTime())){setFormError("Informe uma data de venda válida.");return;}
  setBusy(true);
  try{
   const keepPhone=!chosen&&mode==="phone"&&phoneComplete(phone);
   const result=await merchantApi.createManualSale(tenantId,{reference,eligible_amount_cents:cents,
    participant_id:chosen?chosen.id:null,reported_paid_at:time.toISOString(),evidence_reference:reference,
    ...(keepPhone?{customer_phone:phone}:{}),...(reward&&chosen?{reward_id:reward.id}:{}),...(creditOn&&chosen?{use_credit:true}:{})});
   setToast(result.already_recorded?"Este cupom já estava registrado. Nada foi duplicado."
    :chosen&&reward?`Venda registrada com o ${reward.title}. Os pontos do vale ficam reservados até a conferência.`
    :chosen&&creditOn?`Venda registrada com ${money(credit)} de crédito. O crédito fica reservado até a conferência.`
    :chosen?(gift?"Venda registrada. O crédito fica pendente até a conferência.":"Venda registrada. Os pontos ficam pendentes até a conferência.")
    :keepPhone?"Venda guardada com o celular do cliente. Vincule quando ele entrar no clube."
    :`Venda registrada sem cliente. Ela não gera ${gift?"crédito":"pontos"} até alguém do clube ser vinculado.`);
   setAmount("");setReceipt("");resetClient();setCustomTime(false);setMore(false);setPaidAt(localNow());
   reload();
  }catch(e){setFormError(e instanceof ApiError?e.message:"Não foi possível registrar a venda.");}
  finally{setBusy(false);}
 };

 const savePhone=async()=>{
  if(busy||!chosen||!pendingPhone)return;setBusy(true);setFormError("");
  try{await merchantApi.setParticipantPhone(tenantId,chosen.id,pendingPhone);
   setPhoneSaved(`Celular salvo no cadastro de ${firstName(chosen.display_name)}.`);setPendingPhone("");}
  catch(e){setFormError(e instanceof ApiError?e.message:"Não foi possível salvar o celular.");}
  finally{setBusy(false);}
 };
 const undo=async(sale:ManualSaleRecord)=>{
  if(busy)return;setBusy(true);setUndoMsg("");setToast("");
  try{await merchantApi.undoManualSale(tenantId,sale.id);setUndoMsg("Venda desfeita."+(sale.redemption?" O vale voltou para o saldo da cliente.":""));reload();}
  catch(e){setUndoMsg(e instanceof ApiError?e.message:"Não foi possível desfazer.");}
  finally{setBusy(false);}
 };

 const who=chosen?firstName(chosen.display_name):"";
 return <>
  <div className="vf-grid2 vs-counter">
   <form className="vf-card vf-sale-form" onSubmit={submit} noValidate aria-label="Registrar venda no balcão">
    <h2 className="vf-h2">Nova venda</h2>
    <div className="vf-field">
     <span id="vf-sale-client-label">{mode==="phone"?"Celular do cliente":"Cliente"}</span>
     {chosen?<div className="vf-sale-chosen">
       <span className="vf-avatar tone-1" aria-hidden="true">{initialsOf(chosen.display_name)}</span>
       <div className="vf-row-main"><strong>{chosen.display_name}</strong>
        <span>{!wallet?chosen.detail:gift?`${money(wallet.credit?.available_cents??wallet.available)} de crédito liberado${wallet.pending?` · ${money(wallet.pending)} a liberar`:""}`
         :`${pts(wallet.available)} pts liberados${wallet.pending?` · ${pts(wallet.pending)} em carência`:""}`}</span></div>
       <button type="button" className="vf-btn is-small" onClick={resetClient}>Trocar</button>
      </div>
     :chosen===null?<div className="vf-sale-chosen is-outside">
       <span className="vf-ico tone-gold" aria-hidden="true"><UserRound size={18}/></span>
       <div className="vf-row-main"><strong>{phoneComplete(phone)&&mode==="phone"?phone+" não está no clube":"Cliente ainda não participa"}</strong>
        <span>{phoneComplete(phone)&&mode==="phone"
         ?"Confira o número. Se a pessoa já é do clube com outro celular (ou sem celular), busque pelo nome."
         :`A venda fica registrada sem ${gift?"crédito":"pontos"}.`}</span>
        {phoneComplete(phone)&&mode==="phone"&&<button type="button" className="vf-btn is-link vs-inline-link"
         onClick={()=>{setPendingPhone(phone);setChosen(undefined);setMode("name");setQuery("");setFormError("");}}>É do clube? Buscar pelo nome</button>}</div>
       <button type="button" className="vf-btn is-small" onClick={resetClient}>Trocar</button>
      </div>
     :mode==="phone"?<>
       <div className="vf-sale-search">
        <Smartphone size={18} aria-hidden="true"/>
        <input id="vf-sale-phone" type="tel" inputMode="tel" aria-labelledby="vf-sale-client-label" autoComplete="off" maxLength={20}
         placeholder="(31) 99999-9999" value={phone} onChange={e=>setPhone(formatPhone(e.target.value))}/>
       </div>
       <small role="status">{phoneState==="looking"?"Procurando no clube…":phoneState==="error"?phoneError
        :phoneDigits(phone).length>=3&&!phoneComplete(phone)?`Continue digitando: ${phoneDigits(phone)[2]==="9"?"celular tem 11 dígitos":"fixo tem 10 dígitos"} com o DDD.`
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

    {chosen&&pendingPhone&&<div className="vs-save-phone" role="group" aria-label="Salvar celular no cadastro">
     <span>Salvar <b>{pendingPhone}</b> no cadastro de {firstName(chosen.display_name)}? Na próxima, é só digitar o celular.</span>
     <div><button type="button" className="vf-btn is-small" onClick={()=>setPendingPhone("")}>Agora não</button>
      <button type="button" className="vf-btn is-small is-primary" disabled={busy} onClick={()=>void savePhone()}>Salvar celular</button></div>
    </div>}
    {phoneSaved&&<div className="vf-toast" role="status"><Check size={18}/>{phoneSaved}</div>}
    {chosen&&gift&&wallet?.pilot_active&&credit>0&&<fieldset className="vs-rewards">
     <legend>{creditOn?"Crédito aplicado nesta compra":`${who} tem crédito para usar agora`}</legend>
     <label className={"vs-reward"+(creditOn?" is-on":"")}>
      <input type="checkbox" checked={creditOn} onChange={()=>setUseCredit(v=>!v)}/>
      <span className="vs-reward-ico" aria-hidden="true"><Gift size={18}/></span>
      <span className="vs-reward-text"><strong>Crédito de {money(credit)}</strong>
       <small>usa todo o crédito · compra mínima {money(gift.min_order_cents)}{wallet?.credit?.in_site_coupon_cents?" · o cupom do site dela será cancelado":""}</small></span>
      <span className="vs-reward-act" aria-hidden="true">{creditOn?"Aplicado":"Usar"}</span>
     </label>
    </fieldset>}
    {chosen&&!gift&&wallet?.pilot_active&&usable.length>0&&<fieldset className="vs-rewards">
     <legend>{reward?"Vale aplicado nesta compra":`${who} pode usar um vale agora`}</legend>
     {usable.map(r=><label key={r.id} className={"vs-reward"+(rewardId===r.id?" is-on":"")}>
      <input type="checkbox" checked={rewardId===r.id} onChange={()=>setRewardId(rewardId===r.id?"":r.id)}/>
      <span className="vs-reward-ico" aria-hidden="true"><Gift size={18}/></span>
      <span className="vs-reward-text"><strong>{r.title}</strong>
       <small>usa {pts(r.points_cost)} pts{r.min_order_cents?` · compra mínima ${money(r.min_order_cents)}`:""}</small></span>
      <span className="vs-reward-act" aria-hidden="true">{rewardId===r.id?"Aplicado":"Usar"}</span>
     </label>)}
    </fieldset>}

    <label className="vf-field" htmlFor="vf-sale-amount">Valor da compra
     <span className="vs-money"><span aria-hidden="true">R$</span>
      <input id="vf-sale-amount" ref={amountRef} inputMode="decimal" autoComplete="off" maxLength={12} placeholder="0,00"
       value={amount} onChange={e=>setAmount(e.target.value)}/></span>
    </label>

    {(reward||creditOn)&&cents!==null&&<div className="vs-calc" aria-label="Conta com o vale">
     <div><span>Compra</span><span>{money(cents)}</span></div>
     <div><span>{reward?reward.title:"Crédito de giftback"}</span><span>− {money(discount)}</span></div>
     <div className="is-total"><span>Cliente paga</span><span>{money(paid??0)}</span></div>
     {rewardProblem&&<p role="alert">{rewardProblem}</p>}
    </div>}

    <details className="vf-sale-more" open={more} onToggle={e=>setMore((e.currentTarget as HTMLDetailsElement).open)}>
     <summary>+ Cupom fiscal ou outra data</summary>
     <label className="vf-field is-compact" htmlFor="vf-sale-receipt">Número do cupom ou recibo (opcional)
      <input id="vf-sale-receipt" maxLength={80} autoComplete="off" placeholder="Ex.: 0042" value={receipt} onChange={e=>setReceipt(e.target.value)}/>
      <small>Ajuda a conferir depois e evita registrar a mesma venda duas vezes.</small>
     </label>
     <button type="button" className="vf-btn is-link" aria-expanded={customTime} onClick={()=>{setCustomTime(v=>!v);setPaidAt(localNow());}}>
      <Clock3 size={15}/> A compra foi em outra data?</button>
     {customTime&&<label className="vf-field is-compact" htmlFor="vf-sale-date">Data e hora da venda
      <input id="vf-sale-date" type="datetime-local" value={paidAt} onChange={e=>setPaidAt(e.target.value)}/></label>}
    </details>

    {formError&&<div className="vf-toast is-error" role="alert"><X size={18}/>{formError}</div>}
    <button type="submit" className="vf-btn is-primary is-big vs-submit" disabled={busy}>
     {busy?"Registrando…":"Registrar venda"}
     {!busy&&chosen&&pilot&&points!==null&&points>0&&<span className="vs-submit-pts">+{gain(points,Boolean(gift))}</span>}
    </button>
    {toast&&<div className="vf-toast" role="status"><Check size={18}/>{toast}</div>}
   </form>

   <aside className="vf-card vs-ticket" aria-labelledby="vs-ticket-title">
    <span id="vs-ticket-title" className="vf-eyebrow">{chosen?`${who} vai receber`:"O cliente vai receber"}</span>
    {points!==null&&chosen!==null?<>
     {gift?<><strong className="vs-ticket-pts">+{money(points)} <small>de crédito</small></strong>
      <span className="vs-ticket-eq">{gift.percent_bps/100}% do valor pago, até {money(gift.cap_cents)} · para usar em compras a partir de {money(gift.min_order_cents)}</span></>
     :<><strong className="vs-ticket-pts">+{pts(points)} <small>pontos</small></strong>
     <span className="vs-ticket-eq">{pointValue!==null?`= ${money(Math.round(points*pointValue/100))} de volta · `:""}
      {rule?`${pts(Math.round(rule.points*10000/rule.per_cents)/100)}% do valor pago`:""}</span></>}
     {wallet&&goal&&projected!==null&&<div className="vs-goal">
      <div className="vs-goal-line"><span>{pts(Math.max(projected,0))} de {pts(goal.points_cost)} pts</span><span>{goal.title}</span></div>
      <div className="vs-bar" role="progressbar" aria-label={"Progresso até "+goal.title} aria-valuemin={0} aria-valuemax={goal.points_cost}
       aria-valuenow={Math.max(projected,0)}><i style={{width:Math.min(100,Math.max(4,projected/goal.points_cost*100))+"%"}}/></div>
     </div>}
     {wallet&&goal&&showTip&&<p className="vs-tip"><Star size={16} aria-hidden="true"/>
      <span>Diga {who?`para ${who}`:"ao cliente"}: “com mais {money(missingCents!)} em compras você ganha {goal.title}.”</span></p>}
     {pilot?<ol className="vs-steps">
      <li>Hoje: <b>venda registrada</b></li>
      <li>Depois da conferência: <b>{gift?"crédito reservado":"pontos reservados"}</b></li>
      <li>{holdDays>0?`Cerca de ${releaseDate}`:"Logo após a conferência"}: <b>{gift?`liberado para usar, por ${gift.validity_days} dias`:"liberados para troca"}</b></li>
     </ol>
     :<p className="vs-off"><TriangleAlert size={16} aria-hidden="true"/>
      <span>{gift?"O giftback está desligado nesta loja: a venda fica registrada, sem gerar crédito. Ative em Meu clube → Como ganhar."
       :"Os pontos estão desligados nesta loja: a venda fica registrada, sem gerar pontos. Ative em Meu clube → Como ganhar."}</span></p>}
    </>
    :<p className="vs-ticket-hint">{chosen===null?`Cliente fora do clube não ganha ${gift?"crédito":"pontos"}. Convide para entrar e as próximas compras contam.`
     :!rule&&!gift?"Defina a regra de pontos em Meu clube para ver a prévia.":gift?"Escolha o cliente e digite o valor para ver o crédito."
     :"Escolha o cliente e digite o valor para ver os pontos."}</p>}
    {!gift&&rule&&pointValue!==null&&<span className="vf-muted vf-small">Cada ponto vale {pointValueText(pointValue)}.</span>}
   </aside>
  </div>

  <section className="vf-card vs-mine" aria-labelledby="vs-mine-title">
   <div className="vf-card-head"><div><h2 id="vs-mine-title" className="vf-h2">Suas vendas de hoje</h2>
    <span className="vf-muted vf-small">Errou? Desfaça em até 5 minutos. Depois disso, recuse em Conferir.</span></div></div>
   {undoMsg&&<div className="vf-toast" role="status"><Undo2 size={18}/>{undoMsg}</div>}
   {mine.length===0?<p className="vf-muted vf-small">Nenhuma venda registrada por você hoje.</p>
   :<ul className="vs-rows">{mine.map(sale=>{const [label,chip]=COUNTER_STATE[sale.state];return <li key={sale.id} className="vs-row">
     <div className="vs-row-main"><strong>{sale.participant_name||"Cliente fora do clube"}</strong>
      <span>{new Date(sale.created_at).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})}
       {sale.redemption?` · ${sale.redemption.title}`:""}</span></div>
     <SaleValue sale={sale} gift={program.mode==="giftback"}/>
     {sale.can_undo?<button type="button" className="vf-btn is-small" disabled={busy} onClick={()=>void undo(sale)}>
      <Undo2 size={15}/> Desfazer</button>:<span className={"vf-chip "+chip}>{label}</span>}
    </li>;})}</ul>}
  </section>
 </>;
}

function SaleValue({sale,gift=false}:{sale:ManualSaleRecord;gift?:boolean}){
 const discount=sale.redemption&&sale.redemption.state!=="cancelled"?sale.redemption.discount_cents:0;
 const points=sale.points_issued??(sale.state==="awaiting_review"?sale.points_preview:null);
 return <div className="vs-val"><strong>{money(sale.eligible_amount_cents-discount)}</strong>
  {sale.participant_id&&typeof points==="number"&&points>0&&sale.state!=="rejected"
   ?<small>{(sale.points_issued?"+":"≈ +")+gain(points,gift)}</small>:null}</div>;
}

/* ---------------- Conferir ---------------- */

function Review({shared}:{shared:Shared}){
 const {tenantId,items,loading,listError,pilot,rule,program,reload}=shared;
 const isGift=program.mode==="giftback";
 const [busy,setBusy]=useState(false);
 const [msg,setMsg]=useState("");
 const [error,setError]=useState("");
 const [rejecting,setRejecting]=useState<string|null>(null);
 const [linking,setLinking]=useState<string|null>(null);
 const [linkTarget,setLinkTarget]=useState("");
 const [people,setPeople]=useState<ProgramParticipant[]>([]);
 const pending=items.filter(i=>i.state==="awaiting_review");
 const noClient=items.filter(i=>i.state==="awaiting_member");
 const clean=pending.filter(i=>!(i.alerts||[]).length);
 const total=pending.reduce((sum,i)=>sum+i.eligible_amount_cents,0);
 const hold=rule?(rule.hold_days===0?"liberados logo":`liberados em ${rule.hold_days} dia${rule.hold_days===1?"":"s"}`):"";

 useEffect(()=>{
  if(!noClient.length)return;
  let active=true;
  merchantApi.listParticipants(tenantId,{status:"active",q:"",offset:0}).then(d=>{if(active)setPeople(d.items);}).catch(()=>{});
  return()=>{active=false};
 },[tenantId,noClient.length]);

 const decide=async(sale:ManualSaleRecord,decision:"approve"|"reject")=>{
  if(busy)return;setBusy(true);setMsg("");setError("");
  try{
   const r=await merchantApi.reviewManualSale(tenantId,sale.id,decision,
    decision==="approve"?"Conferida pelo lojista no painel.":"Recusada pelo lojista no painel.");
   const name=sale.participant_name?firstName(sale.participant_name):"a cliente";
   const none=isGift?"nenhum crédito foi gerado":"nenhum ponto foi creditado";
   setMsg(decision==="reject"?`Venda recusada: ${none}.`+(sale.redemption?(isGift?" O crédito usado voltou para a cliente.":" O vale voltou para o saldo."):"")
    :r.points?`Venda confirmada: +${isGift?money(r.points)+" de crédito":pts(r.points)+" pontos"} para ${name}, ${isGift&&program.mode==="giftback"?(program.hold_days===0?"liberado logo":`liberado em ${program.hold_days} dias`):hold}.`
    :r.points_reason==="budget"?`Venda confirmada, mas o orçamento total acabou: ${none}. Aumente em Meu clube → Como ganhar.`
    :r.points_reason==="before_join"?`Venda confirmada. Ela é anterior à entrada no clube, por isso não gera ${isGift?"crédito":"pontos"}.`
    :pilot?`Venda confirmada. Esta venda não gera ${isGift?"crédito":"pontos"}.`
    :`Venda conferida: ${none}, porque ${isGift?"o giftback está desligado":"os pontos estão desligados"} nesta loja.`);
   setRejecting(null);reload();
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível concluir a conferência.");}
  finally{setBusy(false);}
 };
 const confirmClean=async()=>{
  if(busy||!clean.length)return;setBusy(true);setMsg("");setError("");
  try{
   const r=await merchantApi.confirmManualSales(tenantId,clean.map(i=>i.id));
   setMsg(`${r.confirmed.length} venda${r.confirmed.length===1?" confirmada":"s confirmadas"}`+(r.points?` · +${isGift?money(r.points)+" de crédito":pts(r.points)+" pontos"}`:"")+
    (r.skipped.length?`. ${r.skipped.length} ficou para conferir uma a uma.`:"."));
   reload();
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível confirmar as vendas.");}
  finally{setBusy(false);}
 };
 const link=async(sale:ManualSaleRecord,target:string)=>{
  if(busy||!target)return;setBusy(true);setMsg("");setError("");
  try{await merchantApi.linkManualSale(tenantId,sale.id,target);setMsg("Cliente vinculado à venda. Agora ela pode ser conferida.");
   setLinking(null);setLinkTarget("");reload();}
  catch(e){setError(e instanceof ApiError?e.message:"É preciso um participante com contato confirmado para vincular.");}
  finally{setBusy(false);}
 };

 return <div className="vs-review">
  <section className="vf-card" aria-labelledby="vs-review-title">
   <div className="vf-card-head vs-head-wrap"><div><h2 id="vs-review-title" className="vf-h2">Vendas do balcão</h2>
    <span className="vf-muted vf-small">{pending.length?`${pending.length} para conferir · ${money(total)}. Confira com o cupom antes de confirmar.`
     :"Confira com o cupom antes de confirmar."}{pilot?(isGift?" O crédito só entra depois de confirmar.":" Os pontos só entram depois de confirmar."):""}</span></div>
    {clean.length>1&&<button type="button" className="vf-btn is-small vs-btn-outline" disabled={busy} onClick={()=>void confirmClean()}>
     <Check size={16}/> Confirmar {clean.length} sem alerta</button>}
   </div>
   {msg&&<div className="vf-toast" role="status"><CheckCircle2 size={18}/>{msg}</div>}
   {(error||listError)&&<div className="vf-toast is-error" role="alert"><X size={18}/>{error||listError}</div>}
   {loading?<p className="vf-muted" role="status">Carregando vendas…</p>
   :pending.length===0?<div className="vs-empty"><CheckCircle2 size={26} aria-hidden="true"/><strong>Tudo conferido</strong>
     <span>Quando alguém registrar uma venda no balcão, ela aparece aqui.</span></div>
   :<ul className="vs-rows">{pending.map((sale,i)=>{const alerts=sale.alerts||[];return <li key={sale.id} className={"vs-row is-review"+(alerts.length?" has-alert":"")}>
     <span className={"vf-avatar "+(alerts.length?"vs-avatar-alert":TONES[i%5])} aria-hidden="true">{initialsOf(sale.participant_name)}</span>
     <div className="vs-row-main"><strong>{sale.participant_name||"Cliente"}</strong>
      <span>{receiptLabel(sale.evidence_reference)} · {when(sale.reported_paid_at||sale.created_at)}{sale.submitted_by_name?` · por ${sale.submitted_by_name}`:""}
       {sale.redemption?` · ${sale.redemption.title}`:""}</span>
      {alerts.length>0&&<span className="vs-alerts">{alerts.map(a=><span key={a} className="vs-alert"><TriangleAlert size={13} aria-hidden="true"/>{a}</span>)}</span>}
     </div>
     <SaleValue sale={sale} gift={program.mode==="giftback"}/>
     {rejecting===sale.id?<div className="vs-acts">
      <button type="button" className="vf-btn is-small" onClick={()=>setRejecting(null)}>Voltar</button>
      <button type="button" className="vf-btn is-small is-danger" disabled={busy} onClick={()=>void decide(sale,"reject")}>Recusar venda</button>
     </div>
     :<div className="vs-acts">
      <button type="button" className="vf-btn is-small vs-ok" disabled={busy} onClick={()=>void decide(sale,"approve")}>
       <Check size={16}/> Confirmar</button>
      <button type="button" className="vf-btn is-small vs-no" disabled={busy} aria-label={"Recusar venda de "+(sale.participant_name||"cliente")}
       onClick={()=>setRejecting(sale.id)}><X size={16}/></button>
     </div>}
    </li>;})}</ul>}
  </section>

  {noClient.length>0&&<section className="vf-card" aria-labelledby="vs-noclient-title">
   <div className="vf-card-head"><div><h2 id="vs-noclient-title" className="vf-h2">Vendas sem cliente</h2>
    <span className="vf-muted vf-small">Vincule quando a pessoa entrar no clube. Só depois a venda pode ser conferida.</span></div></div>
   <ul className="vs-rows">{noClient.map(sale=><li key={sale.id} className="vs-row is-review">
    <span className="vf-ico tone-gold" aria-hidden="true"><UserRound size={18}/></span>
    <div className="vs-row-main"><strong>Cliente fora do clube</strong>
     <span>{receiptLabel(sale.evidence_reference)} · {when(sale.reported_paid_at||sale.created_at)}</span></div>
    <SaleValue sale={sale} gift={program.mode==="giftback"}/>
    <div className="vs-acts">
     {sale.suggested_participant?<button type="button" className="vf-btn is-small is-primary" disabled={busy} onClick={()=>void link(sale,sale.suggested_participant!.id)}>
      <Link2 size={15}/> Vincular a {sale.suggested_participant.display_name}</button>
     :linking===sale.id?<span className="vs-link">
      <select aria-label="Participante para vincular" value={linkTarget} onChange={e=>setLinkTarget(e.target.value)}>
       <option value="" disabled>Selecione</option>
       {people.map(p=><option key={p.id} value={p.id}>{p.display_name} · {p.contact_email}</option>)}
      </select>
      <button type="button" className="vf-btn is-small is-primary" disabled={busy||!linkTarget} onClick={()=>void link(sale,linkTarget)}>Vincular</button>
     </span>
     :<button type="button" className="vf-btn is-small" onClick={()=>{setLinking(sale.id);setLinkTarget("");}}>Vincular cliente</button>}
    </div>
   </li>)}</ul>
  </section>}
 </div>;
}

/* ---------------- Pedidos ---------------- */

type Row={key:string;channel:"counter"|"site";title:string;sub:string;cents:number;points:string;status:[string,string];
 dim:boolean;club:boolean;at:number;search:string;initials:string|null};
const SITE_STATUS=(o:PaidOrderInspection):[string,string]=>{
 if(o.review_status==="blocked_cancelled")return ["Cancelado","is-danger"];
 if(o.review_status==="blocked_refund"||o.review_status==="blocked_chargeback")return ["Estornado","is-danger"];
 if(o.payment_status==="paid")return ["Pago","is-ok"];
 return ["Aguardando pagamento","is-gold"];
};

function Orders({shared}:{shared:Shared}){
 const {tenantId,items,loading,listError,program,reload}=shared;
 const isGift=program.mode==="giftback";
 const noneLabel=isGift?"sem crédito":"sem pontos";
 const [site,setSite]=useState<PaidOrderInspection[]>([]);
 const [siteState,setSiteState]=useState<"loading"|"ok"|"off">("loading");
 const [siteMsg,setSiteMsg]=useState("");
 const [siteRev,setSiteRev]=useState(0);
 const [q,setQ]=useState("");
 const [channel,setChannel]=useState<"all"|"counter"|"site">("all");
 const [status,setStatus]=useState<"all"|"open"|"done"|"cancelled">("all");
 const [clubOnly,setClubOnly]=useState(false);

 useEffect(()=>{
  let active=true;setSiteState("loading");setSiteMsg("");
  merchantApi.recentNuvemshopOrders(tenantId).then(r=>{if(active){setSite(r.items);setSiteState("ok");}})
   .catch(e=>{if(!active)return;setSiteState("off");
    setSiteMsg(e instanceof ApiError&&e.status===429?"A loja acabou de ser consultada. Atualize em alguns segundos."
     :e instanceof ApiError&&e.status===409?(e.message.includes("recusou")?e.message:"Pedidos do site indisponíveis: confira a conexão em Configurações.")
     :e instanceof ApiError&&e.status===503?"Pedidos do site indisponíveis: integração não configurada no servidor."
     :e instanceof ApiError&&e.status===404?"Esta loja não tem site conectado.":"Não foi possível ler os pedidos do site agora.");});
  return()=>{active=false};
 },[tenantId,siteRev]);

 const rows=useMemo<Row[]>(()=>{
  const counter:Row[]=items.map(s=>{const discount=s.redemption&&s.redemption.state!=="cancelled"?s.redemption.discount_cents:0;
   const p=s.points_issued??(s.state==="awaiting_review"?s.points_preview:null);
   return {key:"c"+s.id,channel:"counter",title:s.participant_name||"Cliente fora do clube",
    sub:when(s.reported_paid_at||s.created_at)+(s.redemption?` · ${s.redemption.title}`:"")+" · "+receiptLabel(s.evidence_reference),
    cents:s.eligible_amount_cents-discount,points:s.participant_id&&typeof p==="number"&&p>0&&s.state!=="rejected"?(s.points_issued?"+":"≈ +")+gain(p,isGift):noneLabel,
    status:COUNTER_STATE[s.state],dim:s.state==="rejected",club:Boolean(s.participant_id),
    at:new Date(s.reported_paid_at||s.created_at).getTime(),initials:s.participant_name,
    search:[s.participant_name,s.reference].join(" ").toLowerCase()};});
  const online:Row[]=site.map(o=>{const st=SITE_STATUS(o);return {key:"s"+o.order_id,channel:"site",
   title:(o.order_number?"#"+o.order_number:"Pedido "+o.order_id)+(o.participant_verified?" · cliente do clube":" · fora do clube"),
   sub:o.paid_at?when(o.paid_at):"sem data de pagamento",cents:o.reported_total_cents,points:noneLabel,status:st,
   dim:st[1]==="is-danger",club:o.participant_verified,at:o.paid_at?new Date(o.paid_at).getTime():0,initials:null,
   search:[o.order_number,o.order_id].join(" ").toLowerCase()};});
  return [...counter,...online].sort((a,b)=>b.at-a.at);
 },[items,site,isGift,noneLabel]);

 const term=q.trim().toLowerCase().replace(/^#/,"");
 const shown=rows.filter(r=>(channel==="all"||r.channel===channel)&&(!clubOnly||r.club)&&(!term||r.search.includes(term))&&
  (status==="all"||(status==="cancelled"?r.dim:status==="open"?(!r.dim&&(r.status[1]==="is-gold"||r.status[1]==="is-soft")):(!r.dim&&r.status[1]==="is-ok"))));

 return <section className="vf-card vs-orders" aria-labelledby="vs-orders-title">
  <div className="vf-card-head vs-head-wrap"><div><h2 id="vs-orders-title" className="vf-h2">Todos os pedidos</h2>
   <span className="vf-muted vf-small">Balcão e site juntos. Compras do site entram sozinhas: não registre no balcão.</span></div>
   <button type="button" className="vf-btn is-small" onClick={()=>{reload();setSiteRev(v=>v+1);}}><RefreshCw size={16}/> Atualizar</button></div>
  <div className="vs-filters">
   <label className="vs-search"><Search size={17} aria-hidden="true"/><span className="vf-sr">Buscar pedido</span>
    <input type="search" value={q} onChange={e=>setQ(e.target.value)} placeholder="Nome, nº do pedido ou cupom" maxLength={80}/></label>
   <label className="vs-select"><span className="vf-sr">Canal</span>
    <select value={channel} onChange={e=>setChannel(e.target.value as typeof channel)}>
     <option value="all">Canal: todos</option><option value="counter">Balcão</option><option value="site">Site</option></select></label>
   <label className="vs-select"><span className="vf-sr">Situação</span>
    <select value={status} onChange={e=>setStatus(e.target.value as typeof status)}>
     <option value="all">Situação: todas</option><option value="open">Em aberto</option><option value="done">Conferidas e pagas</option>
     <option value="cancelled">Canceladas e recusadas</option></select></label>
   <label className="vs-toggle"><input type="checkbox" checked={clubOnly} onChange={e=>setClubOnly(e.target.checked)}/> Só clientes do clube</label>
  </div>
  {listError&&<div className="vf-toast is-error" role="alert">{listError}</div>}
  {siteState==="off"&&siteMsg&&<div className="vf-toast is-info" role="status">{siteMsg}</div>}
  {loading&&siteState==="loading"?<p className="vf-muted" role="status">Carregando pedidos…</p>
  :shown.length===0?<div className="vs-empty"><ShoppingBag size={24} aria-hidden="true"/><strong>Nenhum pedido encontrado</strong>
    <span>{rows.length?"Mude a busca ou os filtros.":"As vendas do balcão e do site aparecem aqui."}</span></div>
  :<ul className="vs-rows" aria-label="Pedidos">{shown.map(r=><li key={r.key} className={"vs-row is-order"+(r.dim?" is-dim":"")}>
    {r.initials?<span className="vf-avatar tone-1" aria-hidden="true">{initialsOf(r.initials)}</span>
     :<span className="vf-avatar vs-avatar-site" aria-hidden="true"><ShoppingBag size={16}/></span>}
    <div className="vs-row-main"><strong>{r.title}</strong><span>{r.sub}</span></div>
    <span className="vs-channel">{r.channel==="counter"?<><StoreIcon size={14} aria-hidden="true"/> Balcão</>:<><ShoppingBag size={14} aria-hidden="true"/> Site</>}</span>
    <div className="vs-val"><strong>{money(r.cents)}</strong><small className={r.points===noneLabel?"is-none":""}>{r.points}</small></div>
    <span className={"vf-chip "+r.status[1]}>{r.status[0]}</span>
   </li>)}</ul>}
  <details className="vf-sale-more"><summary>Consultar um pedido pelo número ou link</summary><PaidOrderCheck tenantId={tenantId}/></details>
 </section>;
}
