import {ArrowRight,HeartHandshake,UsersRound,Gift,FlaskConical,PlugZap,Settings2} from "lucide-react";
import {useEffect,useState} from "react";
import EnrollmentManagement from "./EnrollmentManagement";
import PointRuleDraftEditor from "./PointRuleDraftEditor";
import RewardDraftEditor from "./RewardDraftEditor";
import LoyaltyTrialPanel from "./LoyaltyTrialPanel";
import {merchantApi,type NuvemshopConnectionStatus,type Store} from "./api";
import "./program-hub.css";

type Area="benefits"|"participants"|"testing";
export default function ProgramHub({tenantId,role,storeSlug,tenantStatus,onViewClients,onViewSales,onOpenSettings}:{
 tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"];
 onViewClients:()=>void;onViewSales:()=>void;onOpenSettings:()=>void;
}){
 const [ruleRefresh,setRuleRefresh]=useState(0);
 const [rewardsRefresh,setRewardsRefresh]=useState(0);
 const [area,setArea]=useState<Area>("benefits");
 const [connection,setConnection]=useState<NuvemshopConnectionStatus|null>(null);
 const [connectionError,setConnectionError]=useState(false);
 useEffect(()=>{
  let active=true;setConnection(null);setConnectionError(false);
  merchantApi.nuvemshopStatus(tenantId).then(result=>{
   if(active)setConnection(result);
  }).catch(()=>{if(active)setConnectionError(true)});
  return()=>{active=false};
 },[tenantId]);

 const connectionTitle=connection?.connected
  ?"Autorização Nuvemshop registrada"
  :connectionError?"Integração não verificada"
  :connection?"Nuvemshop ainda não autorizada":"Consultando a integração…";
 const ordersTitle=connection?.order_verification?.read_only_preview_available
  ?"Leitura de pedidos disponível"
  :connection?.order_verification?.order_scope_granted
  ?"Leitura de pedidos aguardando habilitação"
  :connection?.connected?"Permissão de pedidos pendente":"Pedidos ainda não conectados";

 return <div className="vf-program-page">
  <section className="vf-program-intro">
   <div><span className="portal-eyebrow">SEU CLUBE DE VANTAGENS</span>
    <h2>Seu clube em três passos.</h2>
    <p>Configure os pontos, divulgue as recompensas e convide clientes.
      Cada tarefa tem seu lugar, sem precisar cadastrar de novo as vendas do site.</p>
   </div>
   <div className="vf-program-intro-actions">
    <a className="vf-program-outline" href={"/clube/"+encodeURIComponent(storeSlug)}
      target="_blank" rel="noopener noreferrer">
      <HeartHandshake size={17}/> Ver Meu Clube <ArrowRight size={16}/>
    </a>
    <button className="vf-program-outline" type="button" onClick={onViewClients}>
     <UsersRound size={17}/> Ver clientes <ArrowRight size={16}/>
    </button>
   </div>
  </section>
  <div className="vf-program-connection" role="status">
    <div className="vf-program-connection-icon"><PlugZap size={19}/></div>
    <div>
      <strong>{connectionTitle}</strong>
      <p>{ordersTitle}. Pontos automáticos e cupons ainda dependem de
        validação financeira; autorização OAuth, sozinha, não comprova pagamento.</p>
    </div>
    <button type="button" onClick={onOpenSettings}>
      <Settings2 size={16}/> Configurações
    </button>
  </div>
  <nav className="vf-program-sections" aria-label="Áreas do programa">
    <button type="button" className={area==="benefits"?"selected":""}
      aria-pressed={area==="benefits"} onClick={()=>setArea("benefits")}>
      <Gift size={17}/> Benefícios
    </button>
    <button type="button" className={area==="participants"?"selected":""}
      aria-pressed={area==="participants"} onClick={()=>setArea("participants")}>
      <UsersRound size={17}/> Participantes
    </button>
    <button type="button" className={area==="testing"?"selected":""}
      aria-pressed={area==="testing"} onClick={()=>setArea("testing")}>
      <FlaskConical size={17}/> Testes
    </button>
  </nav>
  {area==="benefits"&&<section className="vf-program-area" aria-label="Configurar benefícios do clube">
    <div className="vf-program-area-heading">
      <h3>Benefícios do seu clube</h3>
      <p>Uma regra de pontos e as recompensas que o cliente poderá consultar.</p>
    </div>
    <PointRuleDraftEditor tenantId={tenantId} role={role}
      onRuleSaved={()=>setRuleRefresh(value=>value+1)}/>
    <RewardDraftEditor tenantId={tenantId} role={role} ruleRefresh={ruleRefresh}
      onDraftsChanged={()=>setRewardsRefresh(value=>value+1)}/>
  </section>}
  {area==="participants"&&<section className="vf-program-area" aria-label="Gerenciar adesões do clube">
    <div className="vf-program-area-heading">
      <h3>Entrada de participantes</h3>
      <p>Regulamento, convites e adesão com consentimento. Os clientes que já fazem parte
        do programa aparecem na área Clientes.</p>
    </div>
    <EnrollmentManagement tenantId={tenantId} role={role} storeSlug={storeSlug}
      tenantStatus={tenantStatus}/>
  </section>}
  {area==="testing"&&<section className="vf-program-area" aria-label="Ferramentas de homologação">
    <div className="vf-program-area-heading">
      <h3>Validar antes de ativar</h3>
      <p>Ferramentas de teste para conferir o funcionamento sem gerar pontos ou cupons reais.</p>
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
    descontos no checkout. A concessão de pontos e o resgate continuam bloqueados
    até a integração de pagamentos ser homologada.
  </p>
 </div>;
}
