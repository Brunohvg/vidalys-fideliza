import {ArrowRight,HeartHandshake,UsersRound,Gift,FlaskConical,PlugZap,Settings2} from "lucide-react";
import {useEffect,useState} from "react";
import EnrollmentManagement from "./EnrollmentManagement";
import PointRuleDraftEditor from "./PointRuleDraftEditor";
import RewardDraftEditor from "./RewardDraftEditor";
import LoyaltyTrialPanel from "./LoyaltyTrialPanel";
import ClubSummaryCard from "./ClubSummaryCard";
import {merchantApi,type NuvemshopConnectionStatus,type Store} from "./api";
import "./program-hub.css";

/* Clube: UM nível de navegação (sem abas dentro de abas). Cada área é uma tarefa. */
export type ProgramArea="rewards"|"earning"|"participants"|"testing";

const areas:{key:ProgramArea;label:string;hint:string;Icon:typeof Gift}[]=[
 {key:"rewards",label:"Recompensas",hint:"O que o cliente troca",Icon:Gift},
 {key:"earning",label:"Regra de pontos",hint:"Como ganhar pontos",Icon:Settings2},
 {key:"participants",label:"Participantes",hint:"Convites e adesões",Icon:UsersRound},
 {key:"testing",label:"Testes",hint:"Simular sem publicar",Icon:FlaskConical},
];

export default function ProgramHub({tenantId,role,storeSlug,tenantStatus,platform,initialArea="rewards",onViewClients,onViewSales,onOpenSettings}:{
 tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"];platform:Store["platform"];
 initialArea?:ProgramArea;
 onViewClients:()=>void;onViewSales:()=>void;onOpenSettings:()=>void;
}){
 const [ruleRefresh,setRuleRefresh]=useState(0);
 const [rewardsRefresh,setRewardsRefresh]=useState(0);
 const [area,setArea]=useState<ProgramArea>(initialArea);
 const [connection,setConnection]=useState<NuvemshopConnectionStatus|null>(null);
 const [connectionError,setConnectionError]=useState(false);
 useEffect(()=>{
  let active=true;setConnection(null);setConnectionError(false);
  merchantApi.nuvemshopStatus(tenantId).then(result=>{
   if(active)setConnection(result);
  }).catch(()=>{if(active)setConnectionError(true)});
  return()=>{active=false};
 },[tenantId]);

 const independentChannel=platform!=="nuvemshop"&&!connection?.connected;
 const connectionTitle=independentChannel
  ?"Clube independente · sem integração obrigatória"
  :connection?.connected
  ?"Autorização Nuvemshop registrada"
  :connectionError?"Integração não verificada"
  :connection?"Nuvemshop ainda não autorizada":"Consultando a integração…";
 const ordersTitle=independentChannel
  ?"Vendas registradas em Vendas → Balcão"
  :connection?.order_verification?.read_only_preview_available
  ?"Leitura de pedidos disponível"
  :connection?.order_verification?.order_scope_granted
  ?"Leitura de pedidos aguardando habilitação"
  :connection?.connected?"Permissão de pedidos pendente":"Pedidos ainda não conectados";

 return <div className="vf-program-page">
  <ClubSummaryCard tenantId={tenantId} role={role} refreshKey={ruleRefresh+":"+rewardsRefresh}/>
  <div className="vf-program-toolbar">
   <nav className="vf-program-sections" aria-label="Áreas do programa">
    {areas.map(({key,label,hint,Icon})=><button key={key} type="button"
      className={area===key?"selected":""} aria-pressed={area===key} onClick={()=>setArea(key)}>
      <Icon size={18}/><span><b>{label}</b><small>{hint}</small></span>
    </button>)}
   </nav>
   <a className="vf-program-outline" href={"/clube/"+encodeURIComponent(storeSlug)}
     target="_blank" rel="noopener noreferrer">
     <HeartHandshake size={17}/> Prévia do Meu Clube <ArrowRight size={16}/>
   </a>
  </div>
  <div className="vf-program-connection vf-program-connection-slim" role="status">
    <PlugZap size={17}/>
    <span>{connectionTitle} · {ordersTitle}.</span>
    <button type="button" onClick={onOpenSettings}>{independentChannel?"Conectar loja online (opcional)":"Ver integração"} <ArrowRight size={15}/></button>
  </div>
  {area==="rewards"&&<section className="vf-program-area vf-program-area-plain" aria-label="Recompensas do clube">
    <RewardDraftEditor tenantId={tenantId} role={role} ruleRefresh={ruleRefresh}
      onDraftsChanged={()=>setRewardsRefresh(value=>value+1)}/>
  </section>}
  {area==="earning"&&<section className="vf-program-area vf-program-area-plain" aria-label="Regra de pontos">
    <PointRuleDraftEditor tenantId={tenantId} role={role}
      onRuleSaved={()=>setRuleRefresh(value=>value+1)}/>
  </section>}
  {area==="participants"&&<section className="vf-program-area" aria-label="Gerenciar adesões do clube">
    <div className="vf-program-area-heading">
      <div>
        <h3>Entrada de participantes</h3>
        <p>Regulamento, convites e adesão com consentimento. Quem já faz parte do clube aparece em Clientes.</p>
      </div>
      <button type="button" className="vf-program-outline vf-program-view-clients"
        onClick={onViewClients}><UsersRound size={16}/> Consultar clientes do clube <ArrowRight size={16}/></button>
    </div>
    <EnrollmentManagement tenantId={tenantId} role={role} storeSlug={storeSlug}
      tenantStatus={tenantStatus}/>
  </section>}
  {area==="testing"&&<section className="vf-program-area" aria-label="Ferramentas de homologação">
    <div className="vf-program-area-heading">
      <div>
        <h3>Validar antes de ativar</h3>
        <p>Confira o funcionamento sem gerar pontos ou cupons reais.</p>
      </div>
    </div>
    <div className="vf-program-operation-link">
      <span>As compras da loja virtual ficam em <strong>Vendas → Nuvemshop</strong>.
        Não registre no balcão um pedido que já existe no site.</span>
      <button type="button" onClick={onViewSales}>
        Acompanhar pedidos <ArrowRight size={16}/>
      </button>
    </div>
    <details className="vf-program-lab">
      <summary>Testar pontos e recompensas sem publicar</summary>
      <LoyaltyTrialPanel tenantId={tenantId} ruleRefresh={ruleRefresh}
        rewardsRefresh={rewardsRefresh}/>
    </details>
  </section>}
  <p className="vf-program-status-note">
    Publicar uma recompensa mostra o benefício no Meu Clube, mas não libera
    descontos no checkout. Pontos e resgates continuam bloqueados até a
    integração de pagamentos ser homologada.
  </p>
 </div>;
}
