import {useEffect,useState} from "react";
import {ArrowRight,CheckCircle2,ClipboardCheck,Gift,PlugZap,ShoppingBag,UsersRound,ShieldCheck} from "lucide-react";
import {merchantApi,type DiscountRewardDraft,type ManualSaleList,
 type NuvemshopConnectionStatus,type ParticipantDirectoryResponse,type Store} from "./api";
import "./action-center.css";

type Destination="program"|"clients"|"sales"|"campaign"|"catalog"|"results"|"settings";
type Data={
 participants:ParticipantDirectoryResponse|null;
 integration:NuvemshopConnectionStatus|null;
 sales:ManualSaleList|null;
 rewards:DiscountRewardDraft[]|null;
 incomplete:boolean;
};
export default function ActionCenter({tenantId,role,onNavigate}:{
 tenantId:string;role:Store["role"];onNavigate:(target:Destination)=>void;
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
    incomplete:people.status==="rejected"||connection.status==="rejected"||
      (canManage&&(sales.status==="rejected"||rewards.status==="rejected")),
   });
  };
  void load();
  return()=>{active=false};
 },[tenantId,canManage]);
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
  }else if(data.integration&&!connected){
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
 return <div className="vf-home" aria-label="Resumo da loja">
  <section className="vf-home-welcome">
   <span className="portal-eyebrow">VISÃO GERAL</span>
   <h2>Seu clube, sem complicação.</h2>
   <p>Uma visão rápida do que existe hoje e do que precisa da sua atenção.</p>
  </section>
  {data?.incomplete&&<p className="vf-home-warning" role="status">
   Alguns dados estão indisponíveis. Um traço não significa zero.
  </p>}
  <section className="vf-home-overview" aria-label="Indicadores reais do clube">
   <article><div><UsersRound size={18}/><span>Participantes ativos</span></div>
    <strong>{data?count??"—":"…"}</strong>
    <small>Adesões registradas</small>
    <button type="button" onClick={()=>onNavigate("clients")}>Ver clientes <ArrowRight size={14}/></button>
   </article>
   <article><div><ClipboardCheck size={18}/><span>Vendas para conferir</span></div>
    <strong>{data?pending??"—":"…"}</strong>
    <small>Até 30 registros do balcão</small>
    <button type="button" onClick={()=>onNavigate("sales")}>Ver vendas <ArrowRight size={14}/></button>
   </article>
   <article><div><Gift size={18}/><span>Recompensas exibidas</span></div>
    <strong>{data?published??"—":"…"}</strong>
    <small>Catálogo do Meu Clube, não cupons liberados</small>
    <button type="button" onClick={()=>onNavigate("program")}>Ver benefícios <ArrowRight size={14}/></button>
   </article>
  </section>
  <section className="vf-home-next" aria-labelledby="vf-home-next-title">
   <div className="vf-home-next-symbol"><CheckCircle2 size={24}/></div>
   <div className="vf-home-next-copy">
    <span className="portal-eyebrow">PRÓXIMA AÇÃO RECOMENDADA</span>
    <h3 id="vf-home-next-title">{data?next.heading:"Verificando sua loja…"}</h3>
    <p>{data?next.detail:"Consultando o estado atual do clube."}</p>
   </div>
   <button type="button" disabled={!data} onClick={()=>onNavigate(next.destination)}>
    {next.button}<ArrowRight size={17}/>
   </button>
  </section>
  <section className="vf-home-integrations" aria-label="Resumo de integração">
   <div className="vf-home-integration-icon"><PlugZap size={20}/></div>
   <div>
    <strong>Nuvemshop</strong>
    <p>{!data?"Verificando a autorização…":
      data.integration===null?"Situação indisponível":
      !connected?"Integração não autorizada nesta loja":
      ordersReady?"Leitura de pedidos habilitada · saldo e cupons ainda não automáticos":
      "Autorização registrada · leitura de pedidos ainda depende de permissão ou configuração"}
    </p>
   </div>
   <button type="button" onClick={()=>onNavigate(connected?"sales":"settings")}>
    {connected?"Ver pedidos":"Conectar"}<ArrowRight size={15}/>
   </button>
  </section>
  <p className="vf-home-safe"><ShieldCheck size={16}/>
   O Fideliza ainda não calcula ROI, vendas atribuídas nem pontos a partir
   de pedidos online. Esses dados só aparecerão quando a integração
   transacional estiver validada.
  </p>
 </div>;
}
