import {ArrowRight, HeartHandshake, UsersRound} from "lucide-react";
import {useState} from "react";
import EnrollmentManagement from "./EnrollmentManagement";
import PointRuleDraftEditor from "./PointRuleDraftEditor";
import RewardDraftEditor from "./RewardDraftEditor";
import LoyaltyTrialPanel from "./LoyaltyTrialPanel";
import PaidOrderCheck from "./PaidOrderCheck";
import type {Store} from "./api";
import "./program-hub.css";

export default function ProgramHub({tenantId,role,storeSlug,tenantStatus,onViewClients}:{
 tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"];
 onViewClients:()=>void;
}){
 const [ruleRefresh,setRuleRefresh]=useState(0);
 const [rewardsRefresh,setRewardsRefresh]=useState(0);
 return <div className="vf-program-page">
  <section className="vf-program-intro">
   <div><span className="portal-eyebrow">SEU CLUBE DE VANTAGENS</span>
    <h2>Seu clube em três passos.</h2>
    <p>Defina uma regra de pontos, publique uma recompensa e convide participantes. O acompanhamento fica em Clientes.</p>
   </div>
   <div className="vf-program-intro-actions">
    <a className="vf-program-outline" href={"/clube/"+encodeURIComponent(storeSlug)}
      target="_blank" rel="noopener noreferrer">
      <HeartHandshake size={17}/> Ver Meu Clube <ArrowRight size={16}/>
    </a>
    <button className="vf-program-outline" type="button" onClick={onViewClients}>
     <UsersRound size={17}/> Ver participantes <ArrowRight size={16}/>
    </button>
   </div>
  </section>
  <nav className="vf-program-steps" aria-label="Configuração do clube">
    <a href="#vf-program-rule"><span>1</span>Regra de pontos</a>
    <a href="#vf-program-rewards"><span>2</span>Recompensas</a>
    <a href="#vf-program-enrollment"><span>3</span>Participantes</a>
  </nav>
  <div id="vf-program-rule" className="vf-program-anchor">
    <PointRuleDraftEditor tenantId={tenantId} role={role}
      onRuleSaved={()=>setRuleRefresh(value=>value+1)}/>
  </div>
  <div id="vf-program-rewards" className="vf-program-anchor">
    <RewardDraftEditor tenantId={tenantId} role={role} ruleRefresh={ruleRefresh}
      onDraftsChanged={()=>setRewardsRefresh(value=>value+1)}/>
  </div>
  <div id="vf-program-enrollment" className="vf-program-anchor">
    <EnrollmentManagement tenantId={tenantId} role={role} storeSlug={storeSlug}
      tenantStatus={tenantStatus}/>
  </div>
  {(role==="owner"||role==="admin")&&tenantStatus==="active"&&
  <details className="vf-program-lab">
    <summary>Conferir pedido Nuvemshop antes de liberar pontos</summary>
    <PaidOrderCheck tenantId={tenantId}/>
  </details>}
  <details className="vf-program-lab">
    <summary>Testar pontos e recompensas sem publicar</summary>
    <LoyaltyTrialPanel tenantId={tenantId} ruleRefresh={ruleRefresh}
      rewardsRefresh={rewardsRefresh}/>
  </details>
  <p className="vf-program-status-note">
    O catálogo de recompensas pode ser publicado no Meu Clube. A regra de
    pontos continua em rascunho: compras ainda não geram pontos e não há
    cupom ou resgate ativo no checkout.
  </p>
 </div>;
}
