import {useEffect,useMemo,useState} from "react";
import {Check,Copy,Info,MessageCircle} from "lucide-react";
import {merchantApi,type CounterWallet,type MemberOffer} from "./api";

/* Página do cliente: mensagem pronta de WhatsApp com o saldo/crédito real da cliente.
   O Fideliza não guarda o celular completo (só HMAC + 4 últimos dígitos), então o link
   abre o WhatsApp do lojista com o texto pronto e ele escolhe o contato. Nada é enviado
   pelo sistema. Campanha só entra para quem aceitou receber ofertas. */

export type MessageKind="balance"|"campaign"|"welcome";
const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const pts=(n:number)=>n.toLocaleString("pt-BR");
const shortDay=(iso:string)=>new Date(iso).toLocaleDateString("pt-BR",{day:"2-digit",month:"2-digit"});
const firstName=(name:string)=>(name||"").trim().split(/\s+/)[0]||"";

export function buildMessage({kind,name,store,clubUrl,wallet,offer}:{kind:MessageKind;name:string;store:string;clubUrl:string;
 wallet:CounterWallet|null;offer?:MemberOffer|null}){
 const hi=`Oi${firstName(name)?", "+firstName(name):""}! Aqui é da loja${store?" "+store:""}.`;
 const club=`Acompanhe no seu clube: ${clubUrl}`;
 if(kind==="campaign"&&offer)return `${hi} ${offer.title}: ${offer.message.trim().replace(/\.?$/,".")} ${club}`;
 const gift=wallet?.program?.mode==="giftback";
 if(kind==="balance"&&wallet){
  const until=wallet.next_expiry?`, até ${shortDay(wallet.next_expiry)}`:"";
  if(gift&&wallet.credit&&wallet.credit.available_cents>0){
   const site=wallet.credit.in_site_coupon_cents?" ou usar o cupom no site":"";
   return `${hi} Você tem ${money(wallet.credit.available_cents)} de crédito para usar com a gente${until}. `+
    `Vale em compras a partir de ${money(wallet.credit.min_order_cents)}: é só informar seu celular no caixa${site}. ${club}`;
  }
  if(gift&&wallet.pending>0)return `${hi} O crédito de ${money(wallet.pending)} da sua última compra já está garantido e libera em breve para usar com a gente. ${club}`;
  const ready=wallet.rewards.filter(r=>r.affordable);
  if(!gift&&ready.length){const best=ready[ready.length-1];
   return `${hi} Você tem ${pts(wallet.available)} pontos e já pode trocar por ${best.title} (${money(best.discount_cents)} de desconto) na próxima compra${until}. É só informar seu celular no caixa. ${club}`;}
  if(!gift&&wallet.next_reward&&wallet.available>0)
   return `${hi} Você tem ${pts(wallet.available)} pontos. Faltam ${pts(wallet.next_reward.missing)} para ganhar ${wallet.next_reward.title} (${money(wallet.next_reward.discount_cents)} de desconto). ${club}`;
 }
 return `${hi} Obrigado por fazer parte do nosso clube! A cada compra você ${gift?"ganha crédito para usar na próxima":"junta pontos que viram desconto"}. ${club}`;
}

export function hasBalance(wallet:CounterWallet|null){
 if(!wallet)return false;
 if(wallet.program?.mode==="giftback")return Boolean((wallet.credit?.available_cents||0)>0||wallet.pending>0);
 return wallet.rewards.some(r=>r.affordable)||Boolean(wallet.next_reward&&wallet.available>0);
}

export default function ClientWhatsApp({tenantId,participantId,name,storeName,clubUrl,phoneLast4,marketing,offers}:{
 tenantId:string;participantId:string;name:string;storeName:string;clubUrl:string;phoneLast4?:string|null;
 marketing:boolean;offers:MemberOffer[]}){
 const [wallet,setWallet]=useState<CounterWallet|null>(null);
 const [loaded,setLoaded]=useState(false);
 const [kind,setKind]=useState<MessageKind|null>(null);
 const [text,setText]=useState("");
 const [edited,setEdited]=useState(false);
 const [copied,setCopied]=useState(false);
 const offer=marketing?offers[0]??null:null;

 useEffect(()=>{
  let active=true;
  merchantApi.counterWallet(tenantId,participantId)
   .then(w=>{if(active)setWallet(w&&Array.isArray(w.rewards)?w:null);})
   .catch(()=>{if(active)setWallet(null);})
   .finally(()=>{if(active)setLoaded(true);});
  return()=>{active=false};
 },[tenantId,participantId]);

 const kinds=useMemo(()=>{
  const list:[MessageKind,string][]=[];
  if(hasBalance(wallet))list.push(["balance",wallet?.program?.mode==="giftback"?"Avisar crédito":"Avisar pontos"]);
  if(offer)list.push(["campaign","Campanha"]);
  list.push(["welcome","Lembrar do clube"]);
  return list;
 },[wallet,offer]);
 const current=kind&&kinds.some(([k])=>k===kind)?kind:kinds[0][0];

 useEffect(()=>{
  if(!loaded||edited)return;
  setText(buildMessage({kind:current,name,store:storeName,clubUrl,wallet,offer}));
 },[loaded,edited,current,name,storeName,clubUrl,wallet,offer]);

 const choose=(k:MessageKind)=>{setKind(k);setEdited(false);};
 const copy=async()=>{try{await navigator.clipboard.writeText(text);setCopied(true);window.setTimeout(()=>setCopied(false),2000);}catch{/* seleção manual */}};
 const href="https://wa.me/?text="+encodeURIComponent(text);

 return <section className="vf-card vf-wa" aria-labelledby="vf-wa-title">
  <div className="vf-wa-head"><span className="vf-wa-ico" aria-hidden="true"><MessageCircle size={18}/></span>
   <div><h2 id="vf-wa-title" className="vf-h3">Mensagem pronta</h2>
    <span className="vf-muted vf-small">Com o saldo de hoje, para enviar pelo seu WhatsApp</span></div></div>
  {!loaded?<p className="vf-muted vf-small" role="status">Montando a mensagem…</p>:<>
   {kinds.length>1&&<div className="vf-wa-kinds" role="radiogroup" aria-label="Tipo de mensagem">
    {kinds.map(([k,label])=><button key={k} type="button" role="radio" aria-checked={current===k}
     className={"vf-wa-kind"+(current===k?" is-on":"")} onClick={()=>choose(k)}>{label}</button>)}
   </div>}
   <label className="vf-wa-field"><span className="vf-sr">Texto da mensagem</span>
    <textarea rows={8} value={text} maxLength={1000} onChange={e=>{setText(e.target.value);setEdited(true);}}/></label>
   <div className="vf-wa-actions">
    <a className="vf-btn is-primary vf-wa-open" href={href} target="_blank" rel="noopener noreferrer"
     aria-disabled={!text.trim()} onClick={e=>{if(!text.trim())e.preventDefault();}}>
     <MessageCircle size={17} aria-hidden="true"/> Abrir no WhatsApp</a>
    <button type="button" className="vf-btn" onClick={()=>void copy()} disabled={!text.trim()}>
     {copied?<><Check size={16} aria-hidden="true"/> Copiado</>:<><Copy size={16} aria-hidden="true"/> Copiar</>}</button>
   </div>
   <p className="vf-wa-hint"><Info size={14} aria-hidden="true"/>
    <span>No WhatsApp, escolha o contato{phoneLast4?` com final ${phoneLast4}`:""}: o Fideliza não guarda o celular completo.
     {!marketing&&" Esta cliente não aceitou ofertas: use só para avisar do saldo, sem promoção."}</span></p>
  </>}
 </section>;
}
