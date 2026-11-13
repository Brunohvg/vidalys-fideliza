import {ArrowRight, HeartHandshake, UsersRound} from "lucide-react";
import EnrollmentManagement from "./EnrollmentManagement";
import PointRuleDraftEditor from "./PointRuleDraftEditor";
import type {Store} from "./api";
import "./program-hub.css";

export default function ProgramHub({tenantId,role,storeSlug,tenantStatus,onViewClients}:{
 tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"];
 onViewClients:()=>void;
}){
 return <div className="vf-program-page">
  <section className="vf-program-intro">
   <div><span className="portal-eyebrow">SEU CLUBE DE VANTAGENS</span>
    <h2>Um programa simples para a loja. Claro para o cliente.</h2>
    <p>Regulamento, divulgação e adesões ficam aqui. Clientes e histórico do programa são acompanhados em áreas próprias.</p>
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
  <EnrollmentManagement tenantId={tenantId} role={role} storeSlug={storeSlug}
   tenantStatus={tenantStatus}/>
  <PointRuleDraftEditor tenantId={tenantId} role={role} />
  <p className="vf-program-status-note">
    A pontuação e os resgates ainda não estão disponíveis.
    As regras são apenas rascunhos e nenhuma compra é pontuada nesta fase.
  </p>
 </div>;
}
