import {useState,type FormEvent} from "react";
import {CheckCircle2,UserPlus,X} from "lucide-react";
import {ApiError,merchantApi} from "./api";
import {formatPhone} from "./phone-mask";

/* Cadastro de cliente pela loja. A cliente precisa ter autorizado (LGPD): quem cadastra declara.
   A participação já nasce ativa; a cliente recebe um e-mail para confirmar e, a partir daí,
   compras no site com esse e-mail geram saldo e ela entra no Meu Clube. */

export default function ClientCreate({tenantId,onCreated,onClose}:{tenantId:string;onCreated:(id:string)=>void;onClose:()=>void}){
 const [name,setName]=useState("");
 const [email,setEmail]=useState("");
 const [phone,setPhone]=useState("");
 const [authorized,setAuthorized]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");

 const submit=async(e:FormEvent)=>{
  e.preventDefault();if(busy)return;setBusy(true);setError("");
  try{
   const r=await merchantApi.createParticipant(tenantId,{name:name.trim(),email:email.trim(),...(phone.trim()?{phone}:{}),authorized});
   onCreated(r.participant.id);
  }catch(err){
   setError(err instanceof ApiError?(err.status===409&&err.message.includes("já está")?err.message+" Busque pelo nome ou e-mail na lista."
    :err.message):"Não foi possível cadastrar agora.");
  }finally{setBusy(false);}
 };

 return <form className="vf-card vf-client-create" aria-labelledby="vf-client-create-title" onSubmit={e=>void submit(e)}>
  <div className="vf-card-head"><div><h2 id="vf-client-create-title" className="vf-h2">Cadastrar cliente</h2>
   <span className="vf-muted vf-small">Ela recebe um e-mail para confirmar. Depois disso, as compras no site com esse e-mail contam sozinhas.</span></div>
   <button type="button" className="vf-btn is-small is-link" onClick={onClose} aria-label="Fechar cadastro"><X size={18}/></button></div>
  <div className="vf-grid2">
   <label className="vf-field is-compact">Nome<input required minLength={3} maxLength={140} autoComplete="off" value={name} onChange={e=>setName(e.target.value)}/></label>
   <label className="vf-field is-compact">E-mail<input type="email" required maxLength={254} autoComplete="off" value={email} onChange={e=>setEmail(e.target.value)}/></label>
   <label className="vf-field is-compact">Celular (opcional)<input type="tel" inputMode="tel" maxLength={20} placeholder="(31) 99999-9999"
    value={phone} onChange={e=>setPhone(formatPhone(e.target.value))}/></label>
  </div>
  <label className="vf-client-phone-check"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/>
   A cliente autorizou entrar no clube e conhece o regulamento</label>
  {error&&<div className="vf-toast is-error" role="alert">{error}</div>}
  <div className="vf-pills">
   <button type="button" className="vf-btn is-small" onClick={onClose}>Cancelar</button>
   <button type="submit" className="vf-btn is-small is-primary" disabled={busy||!authorized||name.trim().length<3||!email.includes("@")}>
    {busy?"Cadastrando…":<><UserPlus size={15}/> Cadastrar</>}</button>
  </div>
  <p className="vf-muted vf-small"><CheckCircle2 size={14} aria-hidden="true"/> Sem autorização da cliente, use o link de convite: ela mesma se cadastra.</p>
 </form>;
}
