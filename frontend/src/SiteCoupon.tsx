import {useState} from "react";
import {Check,Clock,Copy,ShoppingBag,Ticket,TriangleAlert} from "lucide-react";
import {ApiError,publicEnrollmentApi,type MemberClubPrivate,type SiteCoupon as Coupon} from "./api";

/* Meu Clube: o cupom único da cliente para usar no site da loja.
   Mesmo saldo do caixa: usar num lugar cancela o outro, sem a cliente precisar fazer nada. */

const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const day=(iso:string)=>new Date(iso).toLocaleDateString("pt-BR",{day:"2-digit",month:"2-digit"});

export function CouponTicket({coupon,counter=true}:{coupon:Coupon;counter?:boolean}){
 const [copied,setCopied]=useState(false);
 /* Criação ainda sem confirmação da loja: sem código (pode não existir) e com o saldo guardado. */
 if(coupon.state!=="issued")return <section className="clb-card clb-ticket-empty clb-ticket-pending" role="status"
  aria-label={"Cupom em confirmação: "+coupon.title}>
  <span className="clb-badge"><Clock size={22} aria-hidden="true"/></span>
  <div><strong>Confirmando seu cupom de {money(coupon.discount_cents)}</strong>
   <span>A loja ainda não confirmou o cupom. Seu saldo está guardado e o código aparece aqui em alguns minutos.</span></div>
 </section>;
 const copy=async()=>{try{await navigator.clipboard.writeText(coupon.code);setCopied(true);window.setTimeout(()=>setCopied(false),2000);}catch{/* seleção manual */}};
 return <section className="clb-ticket" aria-label={"Cupom para o site: "+coupon.title}>
  <div className="clb-ticket-top">
   <span className="clb-eyebrow"><ShoppingBag size={14} aria-hidden="true"/> USE NO SITE</span>
   <strong className="clb-ticket-value">{money(coupon.discount_cents)}</strong>
   <span className="clb-ticket-rule">{coupon.source==="reward"?coupon.title+" · ":""}compra a partir de {money(coupon.min_order_cents)} · até {day(coupon.expires_at)}</span>
  </div>
  <div className="clb-ticket-cut" aria-hidden="true"/>
  <div className="clb-ticket-bottom">
   <div className="clb-ticket-code"><code>{coupon.code}</code>
    <button type="button" className="clb-btn is-light is-small" onClick={()=>void copy()} aria-label={"Copiar cupom "+coupon.code}>
     {copied?<><Check size={16} aria-hidden="true"/> Copiado</>:<><Copy size={16} aria-hidden="true"/> Copiar</>}</button></div>
   {coupon.apply_url&&<a className="clb-btn is-primary" href={coupon.apply_url} target="_blank" rel="noopener noreferrer">Comprar com o cupom</a>}
   <small>{counter?"Vale uma vez. Se preferir usar no caixa, é só dizer seu celular: o cupom do site é cancelado sozinho."
    :"Vale uma vez, no carrinho do site. Compre com o mesmo e-mail do clube para ganhar crédito de novo."}</small>
  </div>
 </section>;
}

export default function SiteCouponArea({slug,me,balance,gift,onChange}:{slug:string;me:MemberClubPrivate;balance:number|null;gift:boolean;
 onChange:(next:MemberClubPrivate)=>void}){
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const site=me.site;
 if(!site?.coupons_enabled)return null;
 const credit=site.coupons.find(c=>c.source==="giftback");
 const create=async()=>{
  if(busy)return;setBusy(true);setError("");
  try{await publicEnrollmentApi.clubCreateCoupon(slug);onChange(await publicEnrollmentApi.clubMe(slug));}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível gerar o cupom agora.");
   publicEnrollmentApi.clubMe(slug).then(onChange).catch(()=>undefined);}
  finally{setBusy(false);}
 };
 if(gift&&credit)return <CouponTicket coupon={credit} counter={me.channels?.counter??true}/>;
 if(gift&&balance!==null&&balance>0)return <section className="clb-card clb-ticket-empty">
  <span className="clb-badge"><Ticket size={22} aria-hidden="true"/></span>
  <div><strong>Prefere comprar no site?</strong><span>Gere um cupom com seu crédito de {money(balance)}. Ele vale uma vez e o desconto sai no carrinho.</span></div>
  <button type="button" className="clb-btn is-primary is-small" disabled={busy} onClick={()=>void create()}>{busy?"Gerando…":"Gerar cupom"}</button>
  {error&&<span className="clb-ticket-error" role="alert"><TriangleAlert size={15} aria-hidden="true"/>{error}</span>}
 </section>;
 return null;
}
