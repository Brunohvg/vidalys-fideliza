import {useEffect,useState} from "react";
import {Check,CirclePause,Mail,CirclePlay,Gift,LockKeyhole,ShieldCheck,ShoppingBag,TriangleAlert} from "lucide-react";
import {ApiError,merchantApi,type CounterPilotState,type Store} from "./api";
import "./store-settings.css";

/* Ativação de pontos/giftback no balcão (Meu clube → Como ganhar). Antes ligável só quando o
   servidor libera a loja. O proprietário ativa, ajusta os tetos e pausa na hora. */

const pts=(n:number)=>n.toLocaleString("pt-BR");
const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});

export default function CounterPilotCard({tenantId,role,refresh=0,onState}:{tenantId:string;role:Store["role"];refresh?:number;onState?:(s:CounterPilotState|null)=>void}){
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
  merchantApi.counterPilot(tenantId).then(s=>{if(!active)return;setState(s);onState?.(s);
   setCap(String(s.per_sale_cap_points/100));setBudget(String(s.budget_points/100));})
   .catch(()=>{if(active){setHidden(true);onState?.(null);}});
  return()=>{active=false};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[tenantId,refresh]);

 const save=async(data:Parameters<typeof merchantApi.setCounterPilot>[1],done:string)=>{
  if(busy)return;setBusy(true);setError("");setNotice("");
  try{const s=await merchantApi.setCounterPilot(tenantId,data);setState(s);onState?.(s);setNotice(done);}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar.");}
  finally{setBusy(false);}
 };
 const saveLimits=()=>{
  const c=Math.round(Number(cap.replace(",","."))*100),b=Math.round(Number(budget.replace(",","."))*100);
  if(!Number.isFinite(c)||c<1||!Number.isFinite(b)||b<1){setError("Informe tetos em reais maiores que zero.");return;}
  void save({per_sale_cap_points:c,budget_points:b},"Tetos salvos.");
 };

 if(hidden||!state)return null;

 if(!state.allowed)return <section id="vf-pilot-card" className="vf-card ss-section" aria-labelledby="ss-pilot-title">
  <div className="vf-row is-top">
   <span className="vf-ico tone-rose" aria-hidden="true"><LockKeyhole size={20}/></span>
   <div className="vf-row-main"><strong id="ss-pilot-title">Ativar no balcão</strong>
    <span>A liberação é feita loja a loja pela equipe Vidalys. Enquanto isso, as vendas são registradas e conferidas, sem gerar pontos nem crédito.</span></div>
   <span className="vf-chip is-soft">Não liberado</span>
  </div>
 </section>;

 const used=state.budget_points?Math.min(100,state.issued_points/state.budget_points*100):0;
 const gift=state.program&&state.program.mode==="giftback"?state.program:null;
 const ready=Boolean(state.rule)||Boolean(gift);
 const unit=gift?"crédito":"pontos";
 return <section id="vf-pilot-card" className="vf-card ss-section ss-pilot" aria-labelledby="ss-pilot-title">
  <div className="vf-card-head"><div><h2 id="ss-pilot-title" className="vf-h2">{gift?"Giftback no balcão":"Pontos no balcão"}</h2>
   <span className="vf-muted vf-small">Ligue quando quiser começar. Pausar congela tudo na hora, sem apagar saldos.</span></div>
   <span className={"vf-chip "+(state.active?"is-ok":"is-gold")}>{state.active?"Ativo":"Pausado"}</span></div>

  <ol className="ss-pilot-steps">
   <li><b>Balcão registra</b> a venda com o celular da cliente.</li>
   <li><b>Você confirma</b> em Vendas → Conferir. Só então {gift?"o crédito entra":"os pontos entram"}, em carência.</li>
   <li><b>A cliente usa no caixa:</b> o vendedor aplica {gift?"o crédito":"o vale"} e o desconto sai na mesma compra.</li>
  </ol>

  <div className="ss-pilot-budget">
   <div className="ss-pilot-line"><span>{gift?"Crédito emitido":"Pontos emitidos"}</span><strong>{gift?`${money(state.issued_points)} de ${money(state.budget_points)}`:`${pts(state.issued_points)} de ${pts(state.budget_points)}`}</strong></div>
   <div className="ss-pilot-bar" role="progressbar" aria-label="Orçamento usado" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(used)}>
    <i style={{width:Math.max(used,2)+"%"}}/></div>
   <span className="vf-muted vf-small">{gift?"":`Equivale a ${money(state.issued_points)} em descontos possíveis. `}Ao atingir o orçamento, novas vendas são conferidas sem gerar {unit}.</span>
  </div>

  {state.notices&&<p className="ss-pilot-mail"><Mail size={16} aria-hidden="true"/>
   <span><b>Avisos automáticos por e-mail:</b> “{gift?"seu crédito liberou":"seus pontos liberaram"}” e “vence em 5 dias”, só para quem confirmou o e-mail e aceitou novidades
    ({state.notices.reachable_members} {state.notices.reachable_members===1?"cliente":"clientes"} hoje{state.notices.emails_queued?` · ${state.notices.emails_queued} avisos enviados`:""}).</span></p>}
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

  {state.site&&<SiteSection site={state.site} gift={Boolean(gift)} owner={owner} busy={busy}
    onToggle={(key,value,done)=>void save({[key]:value},done)}/>}

  {owner?<>
   <div className="vf-grid2 ss-pilot-limits">
    <label className="vf-field is-compact">Teto por venda (R$)
     <input inputMode="decimal" value={cap} onChange={e=>setCap(e.target.value)} disabled={busy}/>
     <small>Uma venda nunca gera mais que isso em {unit}. Sugestão: R$ 15 (ou o teto do giftback).</small></label>
    <label className="vf-field is-compact">Orçamento total (R$)
     <input inputMode="decimal" value={budget} onChange={e=>setBudget(e.target.value)} disabled={busy}/>
     <small>Soma de tudo que pode ser emitido. Sugestão para começar: R$ 500.</small></label>
   </div>
   {error&&<div className="vf-toast is-error" role="alert"><TriangleAlert size={18}/>{error}</div>}
   {notice&&<div className="vf-toast" role="status"><Check size={18}/>{notice}</div>}
   <div className="ss-actions ss-pilot-actions">
    <button type="button" className="vf-btn" disabled={busy} onClick={saveLimits}>Salvar tetos</button>
    {state.active?<button type="button" className="vf-btn is-danger" disabled={busy}
      onClick={()=>void save({active:false},gift?"Pausado. Novas conferências não geram crédito e o crédito não pode ser usado.":"Pausado. Novas conferências não geram pontos e vales não podem ser usados.")}>
      <CirclePause size={18}/> Pausar agora</button>
     :<button type="button" className="vf-btn is-primary" disabled={busy||!ready}
      onClick={()=>void save({active:true},"Ativado. Confirme as próximas vendas em Vendas → Conferir.")}>
      <CirclePlay size={18}/> Ativar no balcão</button>}
   </div>
  </>:<p className="vf-note"><ShieldCheck size={16}/> Só o proprietário ativa, pausa ou muda os tetos.</p>}
 </section>;
}

type Site=NonNullable<CounterPilotState["site"]>;
type SiteKey="online_earning"|"online_coupons"|"coupon_combines"|"coupons_paused";

/* Site (Nuvemshop): o que já funciona, o que falta e as escolhas do lojista, em linguagem simples. */
function SiteSection({site,gift,owner,busy,onToggle}:{site:Site;gift:boolean;owner:boolean;busy:boolean;
 onToggle:(key:SiteKey,value:boolean,done:string)=>void}){
 const unit=gift?"crédito":"pontos";
 const checks:[boolean,string,string][]=[
  [site.connected,"Loja Nuvemshop conectada","Conecte em Configurações → Canais de venda."],
  [site.orders_scope&&site.webhooks,"Pedidos do site chegando sozinhos","Falta liberar a leitura de pedidos e os avisos de pedido no servidor."],
  [site.coupons_scope,"Permissão para criar cupons","Em Configurações → Canais, clique Atualizar conexão e aceite a permissão de Cupons."],
  [site.coupons_server,"Cupons ligados no servidor","Falta ligar a criação de cupons na hospedagem (variável de cupons)."],
 ];
 const toggles:[SiteKey,boolean,string,string,boolean][]=[
  ["online_earning",site.online_earning,`Compras pagas no site geram ${unit}`,"Sem conferir: o pedido pago já conta. Cancelou na carência, sai.",site.earning_ready],
  ["online_coupons",site.online_coupons,"Resgate por cupom único no site",gift?"O crédito liberado vira um cupom da cliente, de uso único, com a compra mínima e a validade do giftback."
   :"A cliente gera o cupom da recompensa no Meu Clube. Uso único, vale 30 dias.",site.coupons_ready],
  ["coupon_combines",site.coupon_combines,"Cupom soma com outras promoções","Desligado é o mais seguro para a margem.",site.coupons_ready],
  ["coupons_paused",site.coupons_paused,"Pausar novos cupons","Use em campanhas como a Black Friday. Cupons já gerados continuam valendo.",site.coupons_ready],
 ];
 return <div className="ss-site" role="group" aria-labelledby="ss-site-title">
  <div className="ss-site-head"><span className="vf-ico tone-purple" aria-hidden="true"><ShoppingBag size={18}/></span>
   <div><strong id="ss-site-title">No site (Nuvemshop)</strong>
    <span>{site.coupons_ready?`${site.coupons_active} cupons ativos · ${site.coupons_used} usados no site`:"Complete os itens abaixo para ligar o site."}</span></div></div>
  <ul className="ss-pilot-checks" aria-label="Situação do site">{checks.map(([ok,title,fix])=><li key={title} className={ok?"is-ok":"is-todo"}>
   {ok?<Check size={15}/>:<TriangleAlert size={15}/>}<span>{title}{ok?"":<small> — {fix}</small>}</span></li>)}</ul>
  <ul className="ss-switches">{toggles.map(([key,on,title,hint,ready])=><li key={key}>
   <div><strong>{title}</strong><small>{hint}</small></div>
   <button type="button" role="switch" aria-checked={on} aria-label={title} className={"ss-switch"+(on?" is-on":"")}
    disabled={!owner||busy||!ready} onClick={()=>onToggle(key,!on,`${title}: ${!on?"ligado":"desligado"}.`)}><span aria-hidden="true"/></button>
  </li>)}</ul>
 </div>;
}

