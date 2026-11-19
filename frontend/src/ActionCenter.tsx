import {useEffect,useState} from "react";
import {giftbackSentence} from "./ProgramModePanel";
import {ArrowRight,CircleDollarSign,ClipboardCheck,Clock3,Gift,MessageCircle,PlugZap,ScrollText,
 Share2,ShieldCheck,ShoppingBag,Sparkles,Star,UserRound} from "lucide-react";
import {merchantApi,type DiscountRewardDraft,type ManualSaleList,
 type NuvemshopConnectionStatus,type ParticipantDirectoryResponse,type PointRuleDraft,
 type ProgramParticipant,type ProgramTermsStatus,type Store} from "./api";
import type {ProgramArea} from "./ProgramHub";
import {percentText,pointValueText,summarizeClub} from "./club-summary";
import "./loyalty-dashboard.css";

/* Início do lojista — réplica do protótipo aprovado: saudação e estágio, o clube
   em uma frase com o anel de progresso, quatro números, "O que fazer agora" e os
   clientes recentes. Só números reais: dado indisponível aparece como "—",
   nunca como zero, e nunca conta como passo concluído. */

type Destination="program"|"clients"|"sales"|"campaign"|"catalog"|"results"|"settings";
type Data={
 participants:ParticipantDirectoryResponse|null;
 integration:NuvemshopConnectionStatus|null;
 sales:ManualSaleList|null;
 rewards:DiscountRewardDraft[]|null;
 rule:PointRuleDraft|null|undefined;   // undefined = não foi possível consultar
 terms:ProgramTermsStatus|null;
 incomplete:boolean;
};
type Tone="gold"|"purple"|"green"|"rose";
type Action={key:string;title:string;detail:string;button:string;tone:Tone;Icon:typeof Star;
 destination:Destination;area?:ProgramArea|"channels";className?:string};

const AVATAR_TONES=["tone-1","tone-2","tone-3","tone-4","tone-5"];
export const initialsOf=(name:string|null|undefined)=>{
 const parts=(name||"").trim().split(/\s+/).filter(Boolean);
 if(!parts.length)return "?";
 return ((parts[0][0]||"")+(parts.length>1?parts[parts.length-1][0]:parts[0][1]||"")).toUpperCase();
};
const greeting=(hour:number)=>hour<12?"Bom dia":hour<18?"Boa tarde":"Boa noite";
const brl=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const DAY=86400000;
const joinedOf=(p:ProgramParticipant)=>p.joined_at||p.consented_at||"";
/** "hoje", "ontem" ou "12 de nov." — sem inventar data quando ela falta. */
export const whenText=(iso:string,now=new Date())=>{
 const date=new Date(iso);
 if(!iso||Number.isNaN(date.getTime()))return "";
 const start=(d:Date)=>new Date(d.getFullYear(),d.getMonth(),d.getDate()).getTime();
 const diff=Math.round((start(now)-start(date))/DAY);
 if(diff===0)return "hoje";
 if(diff===1)return "ontem";
 return date.toLocaleDateString("pt-BR",{day:"2-digit",month:"short"});
};
const channelOf=(p:ProgramParticipant)=>p.nuvemshop_customer_linked||p.consent_channel==="storefront_opt_in"
 ?"Site":p.manual_sales_count>0?"Balcão":"Convite";
const periodText=(days:number)=>days%365===0?`${days/365} ano${days===365?"":"s"}`:`${days} dia${days===1?"":"s"}`;

/** Número que conta do zero ao valor real; quem desliga animação vê o valor direto. */
function useCountUp(target:number|null|undefined){
 const [value,setValue]=useState(0);
 useEffect(()=>{
  if(typeof target!=="number")return;
  const reduce=typeof window!=="undefined"&&window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if(reduce||target===0){setValue(target);return;}
  let frame=0;const start=performance.now();
  const step=(now:number)=>{
   const progress=Math.min(1,(now-start)/800);
   setValue(Math.round(target*(1-Math.pow(1-progress,3))));
   if(progress<1)frame=requestAnimationFrame(step);
  };
  frame=requestAnimationFrame(step);
  return()=>cancelAnimationFrame(frame);
 },[target]);
 return typeof target==="number"?value:null;
}

export default function ActionCenter({tenantId,role,platform,userName,onNavigate}:{
 tenantId:string;role:Store["role"];platform:Store["platform"];userName?:string;
 onNavigate:(target:Destination,area?:ProgramArea|"channels")=>void;
}){
 const canManage=role==="owner"||role==="admin";
 const [data,setData]=useState<Data|null>(null);
 useEffect(()=>{
  let active=true;setData(null);
  const load=async()=>{
   const [people,connection,sales,rewards,rule,terms]=await Promise.allSettled([
    merchantApi.listParticipants(tenantId),
    merchantApi.nuvemshopStatus(tenantId),
    canManage?merchantApi.listManualSales(tenantId):Promise.resolve(null),
    canManage?merchantApi.listDiscountRewardDrafts(tenantId):Promise.resolve(null),
    canManage?merchantApi.getPointRuleDraft(tenantId):Promise.resolve(null),
    canManage?merchantApi.currentProgramTerms(tenantId):Promise.resolve(null),
   ]);
   if(!active)return;
   setData({
    participants:people.status==="fulfilled"?people.value:null,
    integration:connection.status==="fulfilled"?connection.value:null,
    sales:sales.status==="fulfilled"?sales.value:null,
    rewards:rewards.status==="fulfilled"&&rewards.value?rewards.value.items:null,
    rule:rule.status==="fulfilled"&&rule.value?rule.value.rule:undefined,
    terms:terms.status==="fulfilled"?terms.value:null,
    incomplete:people.status==="rejected"||(platform==="nuvemshop"&&connection.status==="rejected")||
      (canManage&&(sales.status==="rejected"||rewards.status==="rejected")),
   });
  };
  void load();
  return()=>{active=false};
 },[tenantId,canManage,platform]);

 const people=data?.participants??null;
 const items=people?.items??[];
 const complete=people!==null&&people.total_filtered<=items.length;
 const members=people?people.summary.active:null;
 const weekNew=complete?items.filter(p=>{const t=new Date(joinedOf(p)).getTime();return !Number.isNaN(t)&&Date.now()-t<7*DAY;}).length:null;
 const balances=items.map(p=>p.points_balance);
 const pointsHeld=complete&&items.length>0&&balances.every(v=>typeof v==="number")
  ?balances.reduce<number>((sum,v)=>sum+(v as number),0):null;
 const pending=data?.sales?data.sales.items.filter(v=>v.state==="awaiting_review").length:null;
 const published=data?.rewards?data.rewards.filter(v=>v.published).length:null;
 const connected=data?.integration?.connected;
 const ordersReady=data?.integration?.order_verification?.read_only_preview_available;

 const summary=data&&canManage?summarizeClub(data.rule??null,data.rewards??[]):null;
 const pv=summary?.pointValue&&summary.pointValue.min===summary.pointValue.max?summary.pointValue.max:null;
 const pointsBrl=(points:number)=>pv===null?null:brl(Math.round(points*pv/100));

 /* Hoje no balcão: registradas hoje (sem recusadas), valor pago e pontos (confirmados + previstos). */
 const todaySales=data?.sales?data.sales.items.filter(v=>v.state!=="rejected"&&new Date(v.created_at).toDateString()===new Date().toDateString()):null;
 const todayCents=todaySales?todaySales.reduce((sum,v)=>sum+v.eligible_amount_cents-(v.redemption&&v.redemption.state!=="cancelled"?v.redemption.discount_cents:0),0):null;
 const todayPoints=todaySales?todaySales.reduce((sum,v)=>sum+(v.points_issued??(v.state==="awaiting_review"&&v.participant_id?v.points_preview??0:0)),0):null;
 const animMembers=useCountUp(members);
 const animPoints=useCountUp(pointsHeld);
 const animPending=useCountUp(pending);
 const animPublished=useCountUp(published);

 /* Passos de montagem: só contam como feitos quando a API confirmou. */
 const gift=data?.sales?.program&&data.sales.program.mode==="giftback"?data.sales.program:null;
 const ruleDone=gift?true:!data||data.rule===undefined?null:data.rule!==null;
 const rewardDone=gift?true:published===null?null:published>0;
 const termsDone=!data||data.terms===null?null:data.terms.terms!==null;
 const inviteDone=members===null?null:members>0;
 const saleDone=!data?.sales?null:data.sales.items.length>0;
 const stepStates=[ruleDone,rewardDone,termsDone,inviteDone,saleDone];
 const doneCount=stepStates.filter(v=>v===true).length;
 const progress=Math.round(doneCount/stepStates.length*100);
 const ready=doneCount===stepStates.length;

 const setup:Action[]=[];
 if(ruleDone===false)setup.push({key:"rule",title:"Definir como o cliente ganha pontos",detail:"Ex.: 1 ponto a cada R$ 1,00, com carência e validade.",
  button:"Definir",tone:"purple",Icon:Sparkles,destination:"program",area:"earning"});
 if(rewardDone===false)setup.push({key:"reward",title:"Publicar a primeira recompensa",detail:"Sem recompensa, os pontos não têm uso para o cliente.",
  button:"Criar",tone:"green",Icon:Star,destination:"program",area:"rewards"});
 if(termsDone===false)setup.push({key:"terms",title:"Aprovar o regulamento do clube",detail:"Regras claras antes do primeiro convite.",
  button:"Aprovar",tone:"purple",Icon:ScrollText,destination:"program",area:"participants"});
 if(inviteDone===false)setup.push({key:"invite",title:"Convidar o primeiro cliente",detail:"Compartilhe o link no caixa, no Instagram e no WhatsApp.",
  button:"Convidar",tone:"gold",Icon:MessageCircle,destination:"program",area:"participants"});
 if(saleDone===false)setup.push({key:"sale",title:"Registrar a primeira venda",detail:"No balcão ou pela Nuvemshop, com conferência.",
  button:"Registrar",tone:"purple",Icon:ShoppingBag,destination:"sales"});
 const actions:Action[]=[];
 if(pending)actions.push({key:"review",title:`Conferir ${pending} venda${pending===1?"":"s"} do balcão`,
  detail:gift?"O crédito só libera depois da conferência.":"Os pontos só liberam depois da conferência.",button:"Conferir",tone:"purple",Icon:ClipboardCheck,destination:"sales"});
 actions.push(...setup.slice(0,pending?2:3));
 if(data&&data.integration!==null)actions.push(connected
  ?{key:"nuvemshop",title:"Consultar pedidos da Nuvemshop",className:"loyalty-dashboard-connection",
    detail:ordersReady?"Leitura de pedidos habilitada; saldo e cupons não são automáticos."
     :"Autorização registrada; leitura de pedidos depende das permissões e configurações.",
    button:"Consultar pedidos",tone:"green",Icon:PlugZap,destination:"sales"}
  :{key:"nuvemshop",title:"Conectar a Nuvemshop",className:"loyalty-dashboard-connection",
    detail:"Integração ainda não autorizada nesta loja.",
    button:"Configurar integração",tone:"gold",Icon:PlugZap,destination:"settings",area:"channels"});

 /* Frase do clube no formato aprovado: % de volta em destaque, valor do ponto, carência e validade. */
 const rule=data?.rule??null;
 const ret=summary?.returnBps??null;
 const hold=rule?(rule.hold_days===0?"libera na hora":`libera em ${periodText(rule.hold_days)}`):"";
 const sentence=!data?null:gift?<>{giftbackSentence(gift)}</>:rule&&ret?<>
   A cada compra, o cliente recebe <strong>{ret.min===ret.max?percentText(ret.max):`de ${percentText(ret.min)} a ${percentText(ret.max)}`} de volta em pontos</strong>.
   {" "}{pv!==null?`Cada ponto vale ${pointValueText(pv)}, `:"O valor do ponto muda conforme a recompensa; "}{hold} e vale por {periodText(rule.validity_days)}.</>
  :rule?<>
   A cada {brl(rule.per_cents)} em compras, o cliente ganha <strong>{rule.points} ponto{rule.points===1?"":"s"}</strong>, que {hold} e vale por {periodText(rule.validity_days)}.
   {" "}Falta publicar a primeira recompensa para o ponto ter valor.</>
  :<>Defina como o cliente ganha pontos e publique a primeira recompensa para ver o resumo do seu clube.</>;

 const firstName=(userName||"").trim().split(/\s+/)[0];
 const recent=[...items].sort((a,b)=>joinedOf(b).localeCompare(joinedOf(a))).slice(0,4);
 const dash=(v:number|null)=>!data?"…":v===null?"—":v.toLocaleString("pt-BR");

 return <div className="vf-home loyalty-dashboard" aria-label="Resumo da loja">
  <header className="loyalty-home-head">
   <div>
    <span className="loyalty-dashboard-eyebrow">{greeting(new Date().getHours()).toUpperCase()}{firstName?", "+firstName.toUpperCase():""}</span>
    <h1 className="loyalty-home-title">Seu clube hoje</h1>
   </div>
   {canManage&&data&&<span className={"loyalty-stage"+(ready?" is-ready":"")}><Clock3 size={14} aria-hidden="true"/>
    {ready?"Pronto para testar":`Em montagem · ${doneCount} de ${stepStates.length} passos`}</span>}
  </header>

  {canManage&&<section className="loyalty-hero" aria-label="Seu clube em uma frase">
   <div className="loyalty-hero-ring" role="progressbar" aria-label="Progresso da configuração"
    aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}
    style={{background:`conic-gradient(var(--vf-gold) 0 ${progress}%, color-mix(in srgb,var(--vf-surface) 20%,transparent) ${progress}% 100%)`}}>
    <span>{data?progress+"%":"…"}</span>
   </div>
   <div className="loyalty-hero-text">
    <span className="loyalty-hero-eyebrow">SEU CLUBE EM UMA FRASE</span>
    <p>{sentence??"Consultando sua loja…"}</p>
   </div>
   {data&&<button type="button" className="loyalty-hero-cta"
    onClick={()=>{const first=setup[0];if(first)onNavigate(first.destination,first.area);else onNavigate("program");}}>
    {setup.length?"Continuar configuração":"Ver meu clube"} <ArrowRight size={16}/></button>}
  </section>}

  {data?.incomplete&&<p className="loyalty-dashboard-warning" role="status">Algumas informações não puderam ser consultadas. Dados indisponíveis aparecem como traço, não como zero.</p>}

  <section className="loyalty-dashboard-metrics" aria-label="Indicadores reais do clube">
   <button type="button" className="loyalty-dashboard-metric" onClick={()=>onNavigate("clients")}>
    <span className="loyalty-metric-top"><span className="loyalty-ico tone-purple"><UserRound size={20}/></span><small>Participantes</small></span>
    <strong>{members===null?dash(null):dash(animMembers)}</strong>
    <span className="loyalty-metric-sub">{weekNew?`+${weekNew} nesta semana`:"adesões confirmadas"}</span>
   </button>
   <button type="button" className="loyalty-dashboard-metric" onClick={()=>onNavigate("clients")}>
    <span className="loyalty-metric-top"><span className="loyalty-ico tone-gold"><CircleDollarSign size={20}/></span><small>{gift?"Crédito com clientes":"Pontos com clientes"}</small></span>
    <strong>{pointsHeld===null?dash(null):gift?brl(animPoints??0):dash(animPoints)}</strong>
    <span className="loyalty-metric-sub">{pointsHeld===null?(gift?"aparece quando o giftback estiver ativo":"aparece quando os pontos estiverem ativos")
     :gift?"crédito liberado das clientes"
     :pointsBrl(pointsHeld)?`equivalem a ${pointsBrl(pointsHeld)}`:"saldo disponível dos participantes"}</span>
   </button>
   <button type="button" className={"loyalty-dashboard-metric"+(pending?" is-attention":"")} onClick={()=>onNavigate("sales")}>
    <span className="loyalty-metric-top"><span className="loyalty-ico tone-rose"><ClipboardCheck size={20}/></span><small>Vendas para conferir</small></span>
    <strong>{pending===null?dash(null):dash(animPending)}</strong>
    <span className="loyalty-metric-sub">{pending?(gift?"crédito aguardando sua conferência":"pontos aguardando sua conferência"):"no balcão, últimos registros"}</span>
   </button>
   <button type="button" className="loyalty-dashboard-metric" onClick={()=>onNavigate("program","rewards")}>
    <span className="loyalty-metric-top"><span className="loyalty-ico tone-green"><Gift size={20}/></span><small>Recompensas publicadas</small></span>
    <strong>{published===null?dash(null):dash(animPublished)}</strong>
    <span className="loyalty-metric-sub">benefícios visíveis no Meu Clube</span>
   </button>
  </section>

  {canManage&&todaySales!==null&&<section className="loyalty-card loyalty-today" aria-labelledby="loyalty-today-title">
   <header><h2 id="loyalty-today-title">Hoje no balcão</h2>
    <button type="button" className="loyalty-pill" onClick={()=>onNavigate("sales")}>Abrir balcão</button></header>
   <dl className="loyalty-today-grid">
    <div><dt>Vendas registradas</dt><dd>{todaySales.length.toLocaleString("pt-BR")}</dd></div>
    <div><dt>Valor pago</dt><dd>{brl(todayCents??0)}</dd></div>
    <div><dt>{gift?"Crédito do dia":"Pontos do dia"}</dt><dd>{gift?brl(todayPoints??0):(todayPoints??0).toLocaleString("pt-BR")}</dd>
     <small>{data?.sales?.pilot_active?"confirmados e a confirmar":gift?"previsto: giftback desligado (ative em Meu clube)":"previstos: pontos desligados (ative em Meu clube)"}</small></div>
   </dl>
  </section>}

  <div className={"loyalty-home-grid"+(canManage?"":" is-single")}>
   {canManage&&<section className="loyalty-card loyalty-checklist" aria-labelledby="loyalty-checklist-title">
    <div className="loyalty-checklist-head"><h2 id="loyalty-checklist-title">O que fazer agora</h2></div>
    {!data?<p className="loyalty-recent-empty">Consultando sua loja…</p>
     :actions.length===0?<p className="loyalty-recent-empty">Tudo em dia. Acompanhe clientes e vendas por aqui.</p>
     :<ul className="loyalty-actions">
      {actions.map(({key,title,detail,button,tone,Icon,destination,area,className})=><li key={key} className={className}>
       <span className={"loyalty-ico tone-"+tone} aria-hidden="true"><Icon size={18}/></span>
       <div><strong>{title}</strong><span>{detail}</span></div>
       <button type="button" className="loyalty-pill" onClick={()=>onNavigate(destination,area)}>{button}</button>
      </li>)}
     </ul>}
   </section>}

   <section className="loyalty-card loyalty-recent" aria-labelledby="loyalty-recent-title">
    <header>
     <h2 id="loyalty-recent-title">Clientes recentes</h2>
     <button type="button" className="loyalty-pill" onClick={()=>onNavigate("clients")}>Ver todos</button>
    </header>
    {!data?<p className="loyalty-recent-empty">Carregando clientes…</p>
     :people===null?<p className="loyalty-recent-empty">Não foi possível consultar os clientes agora.</p>
     :recent.length===0?<div className="loyalty-recent-empty">
       <p>Ninguém entrou no clube ainda. Compartilhe o convite no caixa, no Instagram e no WhatsApp.</p>
       {canManage&&<button type="button" className="loyalty-pill" onClick={()=>onNavigate("program","participants")}><Share2 size={15}/> Compartilhar convite</button>}
      </div>
     :<ul>
       {recent.map((person,index)=>{
        const when=whenText(joinedOf(person));
        const pts=person.points_balance;
        const money=typeof pts==="number"?pointsBrl(pts):null;
        return <li key={person.id}>
         <span className={"loyalty-avatar "+AVATAR_TONES[index%AVATAR_TONES.length]} aria-hidden="true">{initialsOf(person.display_name)}</span>
         <div className="loyalty-recent-who"><strong>{person.display_name}</strong>
          <span>{channelOf(person)}{when?" · "+when:""}</span></div>
         <div className="loyalty-recent-points">
          <strong>{typeof pts==="number"?pts.toLocaleString("pt-BR")+" pts":"—"}</strong>
          {money&&<span>{money}</span>}
         </div>
        </li>;})}
      </ul>}
   </section>
  </div>

  <p className="loyalty-dashboard-disclosure"><ShieldCheck size={15}/> Só números verificados. O Fideliza ainda não calcula ROI, vendas atribuídas ou pontos de pedidos online.</p>
 </div>;
}
