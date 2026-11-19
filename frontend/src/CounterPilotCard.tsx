import {useEffect,useState} from "react";
import {Check,CirclePause,CirclePlay,Gift,LockKeyhole,ShieldCheck,TriangleAlert} from "lucide-react";
import {ApiError,merchantApi,type CounterPilotState,type Store} from "./api";

/* Piloto de pontos no balcão (Configurações → Canais). Só aparece ligável quando o
   servidor libera a loja. O proprietário ativa, ajusta os tetos e pausa na hora. */

const pts=(n:number)=>n.toLocaleString("pt-BR");
const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});

export default function CounterPilotCard({tenantId,role}:{tenantId:string;role:Store["role"]}){
 const owner=role==="owner";
 const [state,setState]=useState<CounterPilotState|null>(null);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [busy,setBusy]=useState(false);
 const [cap,setCap]=useState("");
 const [budget,setBudget]=useState("");
 const [hidden,setHidden]=useState(false);

 useEffect(()=>{
  let active=true;
  merchantApi.counterPilot(tenantId).then(s=>{if(!active)return;setState(s);
   setCap(String(s.per_sale_cap_points/100));setBudget(String(s.budget_points/100));})
   .catch(()=>{if(active)setHidden(true);});
  return()=>{active=false};
 },[tenantId]);

 const save=async(data:{active?:boolean;per_sale_cap_points?:number;budget_points?:number},done:string)=>{
  if(busy)return;setBusy(true);setError("");setNotice("");
  try{const s=await merchantApi.setCounterPilot(tenantId,data);setState(s);setNotice(done);}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar.");}
  finally{setBusy(false);}
 };
 const saveLimits=()=>{
  const c=Math.round(Number(cap.replace(",","."))*100),b=Math.round(Number(budget.replace(",","."))*100);
  if(!Number.isFinite(c)||c<1||!Number.isFinite(b)||b<1){setError("Informe tetos em reais maiores que zero.");return;}
  void save({per_sale_cap_points:c,budget_points:b},"Tetos salvos.");
 };

 if(hidden||!state)return null;

 if(!state.allowed)return <section className="vf-card ss-section" aria-labelledby="ss-pilot-title">
  <div className="vf-row is-top">
   <span className="vf-ico tone-rose" aria-hidden="true"><LockKeyhole size={20}/></span>
   <div className="vf-row-main"><strong id="ss-pilot-title">Pontos no balcão</strong>
    <span>A liberação é feita loja a loja pela equipe Vidalys. Enquanto isso, as vendas são registradas e conferidas, sem crédito de pontos.</span></div>
   <span className="vf-chip is-soft">Não liberado</span>
  </div>
 </section>;

 const used=state.budget_points?Math.min(100,state.issued_points/state.budget_points*100):0;
 const gift=state.program&&state.program.mode==="giftback"?state.program:null;
 const ready=Boolean(state.rule)||Boolean(gift);
 return <section className="vf-card ss-section ss-pilot" aria-labelledby="ss-pilot-title">
  <div className="vf-card-head"><div><h2 id="ss-pilot-title" className="vf-h2">Piloto de pontos no balcão</h2>
   <span className="vf-muted vf-small">Teste controlado: só esta loja, só no ambiente de homologação.</span></div>
   <span className={"vf-chip "+(state.active?"is-ok":"is-gold")}>{state.active?"Ativo":"Pausado"}</span></div>

  <ol className="ss-pilot-steps">
   <li><b>Balcão registra</b> a venda com o celular da cliente.</li>
   <li><b>Você confirma</b> em Vendas → Conferir. Só então os pontos entram, em carência.</li>
   <li><b>A cliente usa no caixa:</b> o vendedor aplica {gift?"o crédito":"o vale"} e o desconto sai na mesma compra.</li>
  </ol>

  <div className="ss-pilot-budget">
   <div className="ss-pilot-line"><span>{gift?"Crédito e pontos emitidos":"Pontos emitidos"}</span><strong>{pts(state.issued_points)} de {pts(state.budget_points)}</strong></div>
   <div className="ss-pilot-bar" role="progressbar" aria-label="Orçamento do piloto usado" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(used)}>
    <i style={{width:Math.max(used,2)+"%"}}/></div>
   <span className="vf-muted vf-small">Equivale a {money(state.issued_points)} em descontos possíveis. Ao atingir o orçamento, novas vendas são conferidas sem pontos.</span>
  </div>

  {gift?<ul className="ss-pilot-checks" aria-label="Antes de ativar">
   <li className="is-ok"><Check size={15}/>Giftback salvo: {gift.percent_bps/100}% de volta · teto {money(gift.cap_cents)} · uso a partir de {money(gift.min_order_cents)} · validade {gift.validity_days} dias</li>
  </ul>
  :<ul className="ss-pilot-checks" aria-label="Antes de ativar">
   <li className={ready?"is-ok":"is-todo"}>{ready?<Check size={15}/>:<TriangleAlert size={15}/>}
    {ready?`Regra de pontos salva: ${pts(Math.round(state.rule!.points*10000/state.rule!.per_cents)/100)}% · carência ${state.rule!.hold_days} dias · validade ${state.rule!.validity_days} dias`
     :"Salve a regra de pontos em Meu clube"}</li>
   <li className={state.counter_rewards?"is-ok":"is-todo"}>{state.counter_rewards?<Gift size={15}/>:<TriangleAlert size={15}/>}
    {state.counter_rewards?`${state.counter_rewards} vale${state.counter_rewards===1?"":"s"} publicado${state.counter_rewards===1?"":"s"} para o balcão`
     :"Publique ao menos um vale com uso no balcão em Meu clube"}</li>
  </ul>}

  {owner?<>
   <div className="vf-grid2 ss-pilot-limits">
    <label className="vf-field is-compact">Teto por venda (R$ em pontos)
     <input inputMode="decimal" value={cap} onChange={e=>setCap(e.target.value)} disabled={busy}/>
     <small>Uma venda nunca gera mais que isso. Sugestão: R$ 15.</small></label>
    <label className="vf-field is-compact">Orçamento total do piloto (R$ em pontos)
     <input inputMode="decimal" value={budget} onChange={e=>setBudget(e.target.value)} disabled={busy}/>
     <small>Soma de tudo que o piloto pode emitir. Sugestão: R$ 500.</small></label>
   </div>
   {error&&<div className="vf-toast is-error" role="alert"><TriangleAlert size={18}/>{error}</div>}
   {notice&&<div className="vf-toast" role="status"><Check size={18}/>{notice}</div>}
   <div className="ss-actions ss-pilot-actions">
    <button type="button" className="vf-btn" disabled={busy} onClick={saveLimits}>Salvar tetos</button>
    {state.active?<button type="button" className="vf-btn is-danger" disabled={busy}
      onClick={()=>void save({active:false},"Piloto pausado. Novas conferências não geram pontos e vales não podem ser usados.")}>
      <CirclePause size={18}/> Pausar agora</button>
     :<button type="button" className="vf-btn is-primary" disabled={busy||!ready}
      onClick={()=>void save({active:true},"Piloto ativo. Confirme as próximas vendas em Vendas → Conferir.")}>
      <CirclePlay size={18}/> Ativar piloto</button>}
   </div>
  </>:<p className="vf-note"><ShieldCheck size={16}/> Só o proprietário ativa, pausa ou muda os tetos.</p>}
 </section>;
}
