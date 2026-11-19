import {useEffect,useMemo,useState} from "react";
import {Check,CircleHelp,Gift,Info,Sparkles,TriangleAlert,Wallet} from "lucide-react";
import {ApiError,merchantApi,type ProgramModeInput,type ProgramModeState} from "./api";

/* Meu clube → Como ganhar: escolher Pontos ou Giftback (um por loja).
   Giftback com valores recomendados, explicação de cada campo e simulação ao vivo. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const PERCENTS=[500,1000,1500];
const CAPS=[1000,2000,3000];
const MINS=[5000,8000,12000];
const VALIDITY=[15,30,60];
const HOLDS=[0,7];
export const RECOMMENDED:ProgramModeInput={mode:"giftback",giftback_bps:1000,giftback_cap_cents:2000,
 giftback_min_order_cents:8000,giftback_validity_days:30,giftback_hold_days:7};

export const giftbackSentence=(g:{percent_bps:number;cap_cents:number;min_order_cents:number;validity_days:number})=>
 `A cada compra, o cliente recebe ${g.percent_bps/100}% de volta em crédito (até ${money(g.cap_cents)}), para usar em até ${g.validity_days} dias numa compra a partir de ${money(g.min_order_cents)}.`;

export default function ProgramModePanel({tenantId,canEdit,onMode}:{tenantId:string;canEdit:boolean;onMode:(mode:"points"|"giftback",saved:boolean)=>void}){
 const [state,setState]=useState<ProgramModeState|null>(null);
 const [draft,setDraft]=useState<ProgramModeInput>(RECOMMENDED);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [hidden,setHidden]=useState(false);

 useEffect(()=>{
  let active=true;
  merchantApi.programMode(tenantId).then(s=>{if(!active)return;setState(s);onMode(s.mode,s.saved);
   setDraft({mode:s.mode,giftback_bps:s.giftback_bps,giftback_cap_cents:s.giftback_cap_cents,giftback_min_order_cents:s.giftback_min_order_cents,
    giftback_validity_days:s.giftback_validity_days,giftback_hold_days:s.giftback_hold_days});})
   .catch(()=>{if(active){setHidden(true);onMode("points",false);}});
  return()=>{active=false};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[tenantId]);

 const ticket=state?.average_ticket_cents||15000;
 const sim=useMemo(()=>{
  const credit=Math.min(Math.floor(ticket*draft.giftback_bps/10000),draft.giftback_cap_cents);
  const capAt=Math.ceil(draft.giftback_cap_cents*10000/draft.giftback_bps);
  return {credit,capAt,cost:draft.giftback_bps/100};
 },[draft,ticket]);
 if(hidden||!state)return null;

 const saved=state.mode;
 const dirty=state.mode!==draft.mode||state.giftback_bps!==draft.giftback_bps||state.giftback_cap_cents!==draft.giftback_cap_cents||
  state.giftback_min_order_cents!==draft.giftback_min_order_cents||state.giftback_validity_days!==draft.giftback_validity_days||
  state.giftback_hold_days!==draft.giftback_hold_days||!state.saved;
 const set=<K extends keyof ProgramModeInput>(key:K,value:ProgramModeInput[K])=>{setDraft(d=>({...d,[key]:value}));setNotice("");};
 const minProblem=draft.giftback_min_order_cents<=draft.giftback_cap_cents?"O pedido mínimo precisa ser maior que o teto do crédito.":"";
 const save=async(next:ProgramModeInput)=>{
  if(busy||!canEdit)return;setBusy(true);setError("");setNotice("");
  try{const s=await merchantApi.saveProgramMode(tenantId,next);setState({...s,average_ticket_cents:state.average_ticket_cents});onMode(s.mode,true);
   setNotice(s.mode==="giftback"?"Giftback salvo. As próximas vendas confirmadas geram crédito em reais.":"Modo pontos salvo. As próximas vendas confirmadas geram pontos.");}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar o modo.");}
  finally{setBusy(false);}
 };
 const Pill=({on,label,onClick}:{on:boolean;label:string;onClick:()=>void})=>
  <button type="button" className={"vf-pill"+(on?" is-on":"")} aria-pressed={on} disabled={!canEdit} onClick={onClick}>{label}</button>;

 return <section className="vf-card pm-root" aria-labelledby="pm-title">
  <div className="vf-card-head"><div><h2 id="pm-title" className="vf-h2">Como o clube devolve valor</h2>
   <span className="vf-muted vf-small">Escolha um modo. Dá para trocar depois; saldos já emitidos continuam valendo.</span></div></div>
  <div className="pm-modes" role="radiogroup" aria-label="Modo do programa">
   {([["points","Pontos","O cliente junta pontos e troca por vales.","Bom para quem compra com frequência e gosta de juntar.",Sparkles],
      ["giftback","Giftback","Cada compra vira crédito em reais para a próxima.","Simples de explicar no caixa. Traz o cliente de volta em poucas semanas.",Gift]] as const)
    .map(([key,title,line,hint,Icon])=><button key={key} type="button" role="radio" aria-checked={draft.mode===key} disabled={!canEdit}
     className={"pm-mode"+(draft.mode===key?" is-on":"")} onClick={()=>set("mode",key)}>
     <span className="pm-mode-ico" aria-hidden="true"><Icon size={20}/></span>
     <span className="pm-mode-text"><strong>{title}{saved===key&&state.saved?<em>em uso</em>:null}</strong><span>{line}</span><small>{hint}</small></span>
    </button>)}
  </div>

  {draft.mode==="giftback"&&<div className="pm-gift">
   <div className="pm-recommend"><Info size={16} aria-hidden="true"/>
    <span><b>Recomendado para começar:</b> 10% de volta, teto de R$ 20, uso em compra a partir de R$ 80, validade de 30 dias e liberação em 7 dias.</span>
    {canEdit&&<button type="button" className="vf-btn is-small" onClick={()=>setDraft(RECOMMENDED)}>Usar recomendado</button>}</div>

   <fieldset className="pm-field"><legend>Quanto volta em crédito</legend>
    <div className="vf-pills" role="group" aria-label="Porcentagem do giftback">
     {PERCENTS.map(v=><Pill key={v} on={draft.giftback_bps===v} label={v/100+"%"} onClick={()=>set("giftback_bps",v)}/>)}</div>
    <small>É o seu custo máximo por venda. 10% é o mais usado no varejo; acima de 15% pesa na margem.</small></fieldset>

   <fieldset className="pm-field"><legend>Teto por compra</legend>
    <div className="vf-pills" role="group" aria-label="Teto do crédito">
     {CAPS.map(v=><Pill key={v} on={draft.giftback_cap_cents===v} label={money(v).replace(",00","")} onClick={()=>set("giftback_cap_cents",v)}/>)}</div>
    <small>Compras grandes não geram crédito sem limite. Com {draft.giftback_bps/100}%, o teto é atingido em compras de {money(sim.capAt)}.</small></fieldset>

   <fieldset className="pm-field"><legend>Compra mínima para usar o crédito</legend>
    <div className="vf-pills" role="group" aria-label="Compra mínima">
     {MINS.map(v=><Pill key={v} on={draft.giftback_min_order_cents===v} label={money(v).replace(",00","")} onClick={()=>set("giftback_min_order_cents",v)}/>)}</div>
    <small>Garante que o crédito puxe uma nova compra, e não vire desconto em compra pequena.</small>
    {minProblem&&<span className="pm-error" role="alert"><TriangleAlert size={14} aria-hidden="true"/>{minProblem}</span>}</fieldset>

   <div className="pm-two">
    <fieldset className="pm-field"><legend>Validade</legend>
     <div className="vf-pills" role="group" aria-label="Validade do crédito">
      {VALIDITY.map(v=><Pill key={v} on={draft.giftback_validity_days===v} label={v+" dias"} onClick={()=>set("giftback_validity_days",v)}/>)}</div>
     <small>Prazo curto cria urgência: o cliente volta antes de esquecer.</small></fieldset>
    <fieldset className="pm-field"><legend>Libera depois de</legend>
     <div className="vf-pills" role="group" aria-label="Liberação do crédito">
      {HOLDS.map(v=><Pill key={v} on={draft.giftback_hold_days===v} label={v===0?"Na hora":v+" dias"} onClick={()=>set("giftback_hold_days",v)}/>)}</div>
     <small>7 dias cobre trocas e devoluções.</small></fieldset>
   </div>

   <div className="pm-sim" aria-live="polite">
    <span className="pm-sim-ico" aria-hidden="true"><Wallet size={20}/></span>
    <div><span className="vf-eyebrow">Simulação{state.average_ticket_cents?" com o seu ticket médio":""}</span>
     <strong>Compra de {money(ticket)} gera {money(sim.credit)} de crédito</strong>
     <span>{draft.giftback_hold_days?`Libera em ${draft.giftback_hold_days} dias e `:"Libera na hora e "}vale por {draft.giftback_validity_days} dias,
      em compras a partir de {money(draft.giftback_min_order_cents)}. Custo máximo: {sim.cost}% da venda, limitado a {money(draft.giftback_cap_cents)}.</span></div>
   </div>
   <p className="pm-sentence"><CircleHelp size={15} aria-hidden="true"/>O cliente lê: “{giftbackSentence({percent_bps:draft.giftback_bps,cap_cents:draft.giftback_cap_cents,
    min_order_cents:draft.giftback_min_order_cents,validity_days:draft.giftback_validity_days})}”</p>
  </div>}

  {draft.mode==="points"&&saved==="giftback"&&<p className="vf-note">Ao voltar para pontos, configure a regra e as recompensas logo abaixo.</p>}
  {error&&<div className="vf-toast is-error" role="alert"><TriangleAlert size={18}/>{error}</div>}
  {notice&&<div className="vf-toast" role="status"><Check size={18}/>{notice}</div>}
  {canEdit&&<div className="vf-club-actions">
   <button type="button" className="vf-btn is-primary" disabled={busy||!dirty||Boolean(draft.mode==="giftback"&&minProblem)} onClick={()=>void save(draft)}>
    {busy?"Salvando…":draft.mode==="giftback"?"Salvar giftback":"Usar pontos"}</button></div>}
 </section>;
}
