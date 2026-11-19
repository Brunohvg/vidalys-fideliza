import {useEffect,useState} from "react";
import {Copy,ShoppingBag} from "lucide-react";
import {merchantApi} from "./api";

/* Meu clube → Participar: compradores recentes do site que ainda não são do clube.
   Só lê os últimos pedidos da Nuvemshop; não envia nada a ninguém. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});

export default function SiteInviteCard({tenantId,joinUrl}:{tenantId:string;joinUrl:string}){
 const [found,setFound]=useState<{count:number;cents:number}|null>(null);
 const [copied,setCopied]=useState(false);
 const [error,setError]=useState("");
 useEffect(()=>{
  let active=true;
  merchantApi.recentNuvemshopOrders(tenantId).then(r=>{
   if(!active)return;
   const outside=r.items.filter(o=>o.payment_status==="paid"&&!o.participant_verified);
   setFound({count:outside.length,cents:outside.reduce((sum,o)=>sum+o.reported_total_cents,0)});
  }).catch(()=>{if(active)setFound(null);});
  return()=>{active=false};
 },[tenantId]);
 if(!found||found.count===0)return null;
 const message=`Oi! Obrigado pela compra. Agora você pode juntar pontos nas próximas compras e trocar por desconto: ${joinUrl}`;
 const copy=async()=>{try{await navigator.clipboard.writeText(message);setCopied(true);window.setTimeout(()=>setCopied(false),2000);}
  catch{setError("Não foi possível copiar. Selecione a mensagem e copie manualmente.");}};
 return <section className="vf-card vf-site-invite" aria-labelledby="vf-site-invite-title">
  <span className="vf-ico tone-gold" aria-hidden="true"><ShoppingBag size={20}/></span>
  <div className="vf-site-invite-text">
   <strong id="vf-site-invite-title" className="vf-h3">{found.count} comprador{found.count===1?"":"es"} recente{found.count===1?"":"s"} do site ainda não {found.count===1?"é":"são"} do clube</strong>
   <span>{money(found.cents)} em compras que não geraram pontos, nos últimos pedidos da loja. Quem entra no clube tem um motivo para voltar.</span>
   <p className="vf-site-invite-msg">{message}</p>
   {error&&<span role="alert" className="vf-site-invite-error">{error}</span>}
  </div>
  <button type="button" className="vf-btn is-small is-primary" onClick={()=>void copy()}><Copy size={15}/> {copied?"Mensagem copiada":"Copiar convite"}</button>
 </section>;
}
