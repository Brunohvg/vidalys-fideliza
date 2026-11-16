import {useEffect,useState} from "react";
import {ArrowRight,CheckCircle2,ClipboardCheck,Gift,PlugZap,UsersRound,ShieldCheck} from "lucide-react";
import {merchantApi,type DiscountRewardDraft,type ManualSaleList,
 type NuvemshopConnectionStatus,type ParticipantDirectoryResponse,type Store} from "./api";
import "./loyalty-dashboard.css";

type Destination="program"|"clients"|"sales"|"campaign"|"catalog"|"results"|"settings";
type Data={
 participants:ParticipantDirectoryResponse|null;
 integration:NuvemshopConnectionStatus|null;
 sales:ManualSaleList|null;
 rewards:DiscountRewardDraft[]|null;
 incomplete:boolean;
};
export default function ActionCenter({tenantId,role,platform,onNavigate}:{
 tenantId:string;role:Store["role"];platform:Store["platform"];onNavigate:(target:Destination)=>void;
}){
 const canManage=role==="owner"||role==="admin";
 const [data,setData]=useState<Data|null>(null);
 useEffect(()=>{
  let active=true;setData(null);
  const load=async()=>{
   const [people,connection,sales,rewards]=await Promise.allSettled([
    merchantApi.listParticipants(tenantId),
    merchantApi.nuvemshopStatus(tenantId),
    canManage?merchantApi.listManualSales(tenantId):Promise.resolve(null),
    canManage?merchantApi.listDiscountRewardDrafts(tenantId):Promise.resolve(null),
   ]);
   if(!active)return;
   setData({
    participants:people.status==="fulfilled"?people.value:null,
    integration:connection.status==="fulfilled"?connection.value:null,
    sales:sales.status==="fulfilled"?sales.value:null,
    rewards:rewards.status==="fulfilled"&&rewards.value?rewards.value.items:null,
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
 let next={
  heading:"Prepare sua loja para fidelizar",
  detail:"Conecte a Nuvemshop ou configure o programa de uma loja física.",
  button:"Abrir Configurações",
  destination:"settings" as Destination,
 };
 if(data){
  if(canManage&&pending!==undefined&&pending>0){
   next={heading:"Confira as vendas do balcão",detail:
    pending+" lançamento(s) aguardando conferência. Isso não concede pontos automaticamente.",
    button:"Conferir vendas",destination:"sales"};
  }else if(data.integration&&!connected&&platform==="nuvemshop"){
   next={heading:"Conecte sua Nuvemshop",detail:
    "Autorize a loja uma vez. Assim o Fideliza poderá ler pedidos sem recadastrá-los manualmente.",
    button:"Configurar integração",destination:"settings"};
  }else if(count===0){
   next={heading:"Convide o primeiro participante",detail:
    "Defina o regulamento e compartilhe o clube. O cliente deve confirmar a adesão.",
    button:"Preparar meu clube",destination:"program"};
  }else if(published===0){
   next={heading:"Prepare a primeira recompensa",detail:
    "Crie o benefício e publique-o para consulta; o resgate só ficará ativo após a integração financeira.",
    button:"Configurar benefícios",destination:"program"};
  }else if(connected){
   next={heading:"Acompanhe as compras do site",detail:
    "Consulte os pedidos na Nuvemshop. A pontuação ainda exige conciliação de pagamento.",
    button:"Ver pedidos",destination:"sales"};
  }else{
   next={heading:"Veja os participantes do clube",detail:
    "Acompanhe adesões e lançamentos registrados, sem métricas inventadas.",
    button:"Ver participantes",destination:"clients"};
  }
 }
 return <div className="vf-home loyalty-dashboard" aria-label="Resumo da loja">
  <section className="loyalty-dashboard-intro">
   <div><span className="loyalty-dashboard-eyebrow">SEU CENTRO DE FIDELIDADE</span>
    <h2>Olá! Seu clube está ganhando forma.</h2>
    <p>Veja quem participa, quais benefícios estão publicados e o que precisa de atenção. Sem números inventados.</p>
   </div>
   <span className="loyalty-dashboard-intro-icon" aria-hidden="true"><Gift size={42}/></span>
  </section>
  {data?.incomplete&&<p className="loyalty-dashboard-warning" role="status">Algumas informações não puderam ser consultadas. Dados indisponíveis aparecem como traço, não como zero.</p>}
  <section className="loyalty-dashboard-metrics" aria-label="Indicadores reais do clube">
   <article className="loyalty-dashboard-metric">
    <div className="loyalty-dashboard-metric-top"><span><UsersRound size={22}/></span><small>Participantes ativos</small></div>
    <strong>{data?count??"—":"…"}</strong>
    <p>Adesões confirmadas nesta loja</p>
    <button type="button" onClick={()=>onNavigate("clients")}>Ver clientes <ArrowRight size={16}/></button>
   </article>
   <article className="loyalty-dashboard-metric">
    <div className="loyalty-dashboard-metric-top"><span><ClipboardCheck size={22}/></span><small>Vendas para conferir</small></div>
    <strong>{data?pending??"—":"…"}</strong>
    <p>Entre os últimos 30 registros de balcão</p>
    <button type="button" onClick={()=>onNavigate("sales")}>Conferir vendas <ArrowRight size={16}/></button>
   </article>
   <article className="loyalty-dashboard-metric">
    <div className="loyalty-dashboard-metric-top"><span><Gift size={22}/></span><small>Recompensas publicadas</small></div>
    <strong>{data?published??"—":"…"}</strong>
    <p>Benefícios visíveis; não são cupons liberados</p>
    <button type="button" onClick={()=>onNavigate("program")}>Ver benefícios <ArrowRight size={16}/></button>
   </article>
  </section>
  <div className="loyalty-dashboard-columns">
   <section className="loyalty-dashboard-next" aria-labelledby="loyalty-dashboard-action">
    <div className="loyalty-dashboard-next-star"><CheckCircle2 size={25}/></div>
    <span className="loyalty-dashboard-eyebrow">SUA PRÓXIMA AÇÃO</span>
    <h3 id="loyalty-dashboard-action">{data?next.heading:"Consultando sua loja…"}</h3>
    <p>{data?next.detail:"Verificando participantes e programa."}</p>
    <button type="button" disabled={!data} onClick={()=>onNavigate(next.destination)}>{next.button}<ArrowRight size={18}/></button>
   </section>
   <section className="loyalty-dashboard-connection" aria-labelledby="loyalty-dashboard-integration">
    <div className="loyalty-dashboard-connection-icon"><PlugZap size={23}/></div>
    <span className="loyalty-dashboard-eyebrow">SEUS CANAIS</span>
    <h3 id="loyalty-dashboard-integration">Nuvemshop</h3>
    <p>{!data?"Verificando conexão…":data.integration===null?"Situação indisponível":!connected?"Integração ainda não autorizada nesta loja":ordersReady?"Leitura de pedidos habilitada; saldo e cupons não são automáticos":"Autorização registrada; leitura de pedidos depende das permissões e configurações"}</p>
    <button type="button" onClick={()=>onNavigate(connected?"sales":"settings")}>{connected?"Consultar pedidos":"Configurar integração"}<ArrowRight size={18}/></button>
   </section>
  </div>
  <p className="loyalty-dashboard-disclosure"><ShieldCheck size={17}/> O Fideliza ainda não calcula ROI, vendas atribuídas ou pontos de pedidos online. Esses indicadores serão exibidos somente após validação transacional.</p>
 </div>;
}
