import {ArrowRight, Gift, HeartHandshake, ShieldCheck, UsersRound} from "lucide-react";
import EnrollmentManagement from "./EnrollmentManagement";
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
   <button className="vf-program-outline" type="button" onClick={onViewClients}>
    <UsersRound size={17}/> Ver participantes <ArrowRight size={16}/>
   </button>
  </section>
  <EnrollmentManagement tenantId={tenantId} role={role} storeSlug={storeSlug}
   tenantStatus={tenantStatus}/>
  <div className="vf-program-next-grid">
   <article><Gift size={21}/><h3>Pontos por compra</h3>
    <p>O acúmulo dependerá de compras pagas e verificadas. O programa ainda não concede pontos automaticamente.</p>
    <span>Motor em desenvolvimento</span>
   </article>
   <article><ShieldCheck size={21}/><h3>Resgate com segurança</h3>
    <p>O cliente só poderá trocar pontos quando a recompensa e sua aplicação no checkout ou caixa estiverem validadas.</p>
    <span>Resgate não habilitado</span>
   </article>
   <article><HeartHandshake size={21}/><h3>Uma identidade, vários canais</h3>
    <p>Nuvemshop é o primeiro canal; o clube terá participantes próprios para atender também vendas físicas e WhatsApp.</p>
    <span>Próxima evolução</span>
   </article>
  </div>
 </div>;
}
