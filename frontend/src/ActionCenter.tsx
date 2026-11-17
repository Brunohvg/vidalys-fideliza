import {useEffect,useState} from "react";
import {ArrowRight,CheckCircle2,ClipboardCheck,Gift,PlugZap,UsersRound,ShieldCheck} from "lucide-react";
import {merchantApi,type DiscountRewardDraft,type ManualSaleList,
 type NuvemshopConnectionStatus,type ParticipantDirectoryResponse,type PointRuleDraft,
 type ProgramTermsStatus,type Store} from "./api";
import type {ProgramArea} from "./ProgramHub";
import "./loyalty-dashboard.css";

/* Início do lojista: (1) o que falta para o clube ir ao ar, (2) números reais,
   (3) canais. Dado indisponível aparece como "—" e nunca conta como passo feito. */

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
type Step={key:string;title:string;detail:string;action:string;done:boolean|null;
 destination:Destination;area?:ProgramArea};

export default function ActionCenter({tenantId,role,platform,onNavigate}:{
 tenantId:string;role:Store["role"];platform:Store["platform"];
 onNavigate:(target:Destination,area?:ProgramArea)=>void;
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

 const count=data?.participants?.summary.active;
 const pending=data?.sales?.items.filter(v=>v.state==="awaiting_review").length;
 const published=data?.rewards?.filter(v=>v.published).length;
 const connected=data?.integration?.connected;
 const ordersReady=data?.integration?.order_verification?.read_only_preview_available;

 const steps:Step[]=[
  {key:"rule",title:"Defina como o cliente ganha pontos",detail:"Ex.: 1 ponto a cada R$ 1,00, com carência e validade.",
   action:"Definir regra",destination:"program",area:"earning",
   done:!data||data.rule===undefined?null:data.rule!==null},
  {key:"reward",title:"Publique a primeira recompensa",detail:"O que o cliente poderá trocar pelos pontos.",
   action:"Criar recompensa",destination:"program",area:"rewards",
   done:published===undefined?null:published>0},
  {key:"terms",title:"Aprove o regulamento do clube",detail:"Regras claras antes do primeiro convite.",
   action:"Aprovar regulamento",destination:"program",area:"participants",
   done:!data||data.terms===null?null:data.terms.terms!==null},
  {key:"invite",title:"Convide o primeiro cliente",detail:"Compartilhe o link; o cliente confirma a adesão por e-mail.",
   action:"Convidar clientes",destination:"program",area:"participants",
   done:count===undefined?null:count>0},
  {key:"sale",title:"Registre a primeira venda",detail:"No balcão ou pela Nuvemshop, com conferência.",
   action:"Registrar venda",destination:"sales",
   done:!data?.sales?null:data.sales.items.length>0},
 ];
 const doneCount=steps.filter(step=>step.done===true).length;
 const next=steps.find(step=>step.done===false);
 const progress=Math.round(doneCount/steps.length*100);

 return <div className="vf-home loyalty-dashboard" aria-label="Resumo da loja">
  {canManage&&<section className="loyalty-checklist" aria-labelledby="loyalty-checklist-title">
   <header className="loyalty-checklist-head">
    <div>
     <span className="loyalty-dashboard-eyebrow">PRIMEIROS PASSOS</span>
     <h2 id="loyalty-checklist-title">Coloque seu clube no ar</h2>
     <p>{!data?"Consultando sua loja…":next?`${doneCount} de ${steps.length} concluídos. Próximo: ${next.title.toLowerCase()}.`
       :doneCount===steps.length?"Tudo pronto. Agora acompanhe clientes e vendas.":"Alguns passos não puderam ser verificados agora."}</p>
    </div>
    {next&&<button type="button" className="loyalty-checklist-cta" onClick={()=>onNavigate(next.destination,next.area)}>
     Continuar <ArrowRight size={18}/></button>}
   </header>
   <div className="loyalty-checklist-bar" role="progressbar" aria-label="Progresso da configuração"
    aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{width:progress+"%"}}/></div>
   <ol className="loyalty-checklist-steps">
    {steps.map((step,index)=><li key={step.key} data-state={step.done===true?"done":step===next?"next":step.done===null?"unknown":"todo"}>
     <span className="loyalty-step-mark" aria-hidden="true">{step.done===true?<CheckCircle2 size={20}/>:index+1}</span>
     <div className="loyalty-step-text">
      <strong>{step.title}</strong>
      <span>{step.done===null&&data?"Não foi possível verificar agora.":step.detail}</span>
     </div>
     {step.done!==true&&<button type="button" className="loyalty-step-action" disabled={!data}
      onClick={()=>onNavigate(step.destination,step.area)}>{step.action}</button>}
     <span className="portal-sr">{step.done===true?"concluído":step.done===null?"não verificado":"pendente"}</span>
    </li>)}
   </ol>
  </section>}

  {data?.incomplete&&<p className="loyalty-dashboard-warning" role="status">Algumas informações não puderam ser consultadas. Dados indisponíveis aparecem como traço, não como zero.</p>}

  <section className="loyalty-dashboard-metrics" aria-label="Indicadores reais do clube">
   <article className="loyalty-dashboard-metric">
    <div className="loyalty-dashboard-metric-top"><span><UsersRound size={20}/></span><small>Participantes ativos</small></div>
    <strong>{data?count??"—":"…"}</strong>
    <p>Adesões confirmadas nesta loja</p>
    <button type="button" onClick={()=>onNavigate("clients")}>Ver clientes <ArrowRight size={15}/></button>
   </article>
   <article className="loyalty-dashboard-metric">
    <div className="loyalty-dashboard-metric-top"><span><ClipboardCheck size={20}/></span><small>Vendas para conferir</small></div>
    <strong>{data?pending??"—":"…"}</strong>
    <p>Entre os últimos 30 registros de balcão</p>
    <button type="button" onClick={()=>onNavigate("sales")}>Conferir vendas <ArrowRight size={15}/></button>
   </article>
   <article className="loyalty-dashboard-metric">
    <div className="loyalty-dashboard-metric-top"><span><Gift size={20}/></span><small>Recompensas publicadas</small></div>
    <strong>{data?published??"—":"…"}</strong>
    <p>Benefícios visíveis; não são cupons liberados</p>
    <button type="button" onClick={()=>onNavigate("program","rewards")}>Ver benefícios <ArrowRight size={15}/></button>
   </article>
   <article className="loyalty-dashboard-metric loyalty-dashboard-connection" aria-labelledby="loyalty-dashboard-integration">
    <div className="loyalty-dashboard-metric-top"><span><PlugZap size={20}/></span><small id="loyalty-dashboard-integration">Nuvemshop</small></div>
    <strong className="loyalty-dashboard-status" data-on={connected?"true":"false"}>{!data?"…":data.integration===null?"—":connected?"Conectada":"Não conectada"}</strong>
    <p>{!data?"Verificando conexão…":data.integration===null?"Situação indisponível":!connected?"Integração ainda não autorizada nesta loja":ordersReady?"Leitura de pedidos habilitada; saldo e cupons não são automáticos":"Autorização registrada; leitura de pedidos depende das permissões e configurações"}</p>
    <button type="button" onClick={()=>onNavigate(connected?"sales":"settings")}>{connected?"Consultar pedidos":"Configurar integração"}<ArrowRight size={15}/></button>
   </article>
  </section>
  <p className="loyalty-dashboard-disclosure"><ShieldCheck size={16}/> O Fideliza ainda não calcula ROI, vendas atribuídas ou pontos de pedidos online. Esses indicadores aparecem somente após validação transacional.</p>
 </div>;
}
