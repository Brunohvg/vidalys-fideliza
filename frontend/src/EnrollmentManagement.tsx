import {useEffect, useState, type FormEvent} from "react";
import {ApiError, merchantApi, type EnrollmentPendingList, type ProgramTerms, type Store} from "./api";
import {ArrowRight, Check, ClipboardCopy, FileCheck2, HeartHandshake, Link2, ShieldCheck} from "lucide-react";
import "./enrollment.css";

export default function EnrollmentManagement({
  tenantId, role
}:{tenantId:string;role:Store["role"]}){
  const [terms,setTerms]=useState<ProgramTerms|null>(null);
  const [pending,setPending]=useState<EnrollmentPendingList|null>(null);
  const [loading,setLoading]=useState(true);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [formOpen,setFormOpen]=useState(false);
  const [version,setVersion]=useState("v1");
  const [title,setTitle]=useState("Regulamento do programa de fidelidade");
  const [body,setBody]=useState("");
  const [busy,setBusy]=useState(false);
  const [link,setLink]=useState("");
  const [copied,setCopied]=useState(false);
  const canEdit=role==="owner"||role==="admin";

  useEffect(()=>{
    if(!canEdit){setLoading(false);return;}
    let active=true;setLoading(true);setError("");setLink("");
    Promise.all([
      merchantApi.currentProgramTerms(tenantId),
      merchantApi.pendingEnrollments(tenantId)
    ]).then(([t,p])=>{
      if(!active)return;
      setTerms(t.terms);setPending(p);
      setFormOpen(!t.terms);
    }).catch(cause=>{
      if(active)setError(cause instanceof ApiError?cause.message:"Falha ao consultar adesões.");
    }).finally(()=>{if(active)setLoading(false)});
    return ()=>{active=false};
  },[tenantId,canEdit]);

  if(!canEdit)return <div className="enroll-quiet">
    <ShieldCheck size={19}/> O administrador da loja prepara convites e termos.
    Seu acesso permite consultar participantes, sem registrar adesões.
  </div>;

  const saveTerms=async(event:FormEvent)=>{
    event.preventDefault();setBusy(true);setError("");setMessage("");setLink("");
    try{
      const result=await merchantApi.approveProgramTerms(tenantId,{
        version:version.trim(),title:title.trim(),body:body.trim()
      });
      setTerms(result.terms);setFormOpen(false);
      setMessage("Versão dos termos registrada. Nenhum benefício foi ativado.");
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível registrar os termos.");
    }finally{setBusy(false);}
  };
  const createLink=async()=>{
    setBusy(true);setError("");setMessage("");setLink("");setCopied(false);
    try{
      const invitation=await merchantApi.createEnrollmentInvitation(tenantId);
      setLink(window.location.origin+"/participar#convite="+invitation.token);
      setMessage("Convite gerado. Compartilhe somente com a pessoa desejada; o link expira em 24 horas.");
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível criar o convite.");
    }finally{setBusy(false);}
  };
  const copyLink=async()=>{
    try{await navigator.clipboard.writeText(link);setCopied(true);}
    catch{setError("Copie o link manualmente pelo campo abaixo.");}
  };
  const startRevision=()=>{
    setFormOpen(true);setVersion("");setBody("");setLink("");setMessage("");
  };

  return <section className="enroll-manager" aria-labelledby="enroll-title">
    <div className="enroll-head">
      <div className="enroll-symbol"><HeartHandshake size={23}/></div>
      <div><span className="portal-eyebrow">ADESÃO COM CONSENTIMENTO</span>
        <h2 id="enroll-title">Prepare seu programa</h2>
        <p>O cliente precisa aceitar voluntariamente. Convite não ativa cashback nem confirma identidade.</p>
      </div>
    </div>
    {loading && <p className="enroll-muted" role="status">Consultando as regras da loja…</p>}
    {error && <div className="enroll-error" role="alert">{error}</div>}
    {message && <div className="enroll-success" role="status"><Check size={16}/>{message}</div>}
    {!loading && <div className="enroll-content">
      <div className="enroll-step">
        <span className="enroll-step-number">01</span>
        <div><strong>Regulamento aprovado</strong>
          <p>{terms?terms.title+" · versão "+terms.version:"Nenhuma versão aprovada ainda."}</p>
        </div>
        {terms && !formOpen && <button type="button" className="enroll-secondary"
          onClick={startRevision}>Nova versão</button>}
      </div>
      {formOpen && <form onSubmit={saveTerms} className="enroll-form">
        <p>Informe o regulamento real da loja. Não use textos fictícios em convites para compradores.</p>
        <div className="enroll-field-row">
          <label>Versão do regulamento
            <input required maxLength={40} value={version} placeholder="Ex.: v1"
              onChange={e=>setVersion(e.target.value)}/>
          </label>
          <label>Título
            <input required maxLength={100} minLength={3} value={title}
              onChange={e=>setTitle(e.target.value)}/>
          </label>
        </div>
        <label>Termos de participação
          <textarea required minLength={80} maxLength={4000} rows={6} value={body}
            placeholder="Descreva a finalidade, as condições, validade, regras de privacidade e direitos do participante."
            onChange={e=>setBody(e.target.value)}/>
        </label>
        <p className="enroll-muted">Revise o texto com o responsável jurídico. Uma nova versão invalida convites antigos ainda não aceitos.</p>
        <div className="enroll-actions">
          {terms && <button type="button" className="enroll-secondary"
            onClick={()=>setFormOpen(false)}>Cancelar</button>}
          <button type="submit" className="portal-primary" disabled={busy||body.trim().length<80}>
            <FileCheck2 size={17}/>{busy?"Registrando…":"Aprovar esta versão"}
          </button>
        </div>
      </form>}
      <div className="enroll-step">
        <span className="enroll-step-number">02</span>
        <div><strong>Convite individual de adesão</strong>
          <p>Link único, válido por 24 horas. Envie manualmente, somente com a autorização necessária.</p>
        </div>
        <button type="button" disabled={!terms||formOpen||busy} className="enroll-secondary"
          onClick={()=>void createLink()}><Link2 size={16}/> Gerar convite</button>
      </div>
      {link && <div className="enroll-share">
        <label>Link gerado para compartilhar (exibido apenas agora)
          <input readOnly value={link} onFocus={e=>e.target.select()}/>
        </label>
        <button type="button" onClick={()=>void copyLink()} className="enroll-secondary">
          {copied?<Check size={16}/>:<ClipboardCopy size={16}/>}
          {copied?"Copiado":"Copiar link"}
        </button>
      </div>}
      <div className="enroll-step">
        <span className="enroll-step-number">03</span>
        <div><strong>Aceites aguardando verificação</strong>
          <p>{pending?pending.total+" aceite(s) registrado(s) sem vínculo de cliente confirmado."
            :"Os aceites serão exibidos aqui depois de recebidos."}</p>
        </div>
        <ArrowRight size={18} aria-hidden="true"/>
      </div>
      {pending && pending.items.length>0 && <div className="enroll-pending-list">
        {pending.items.map(item=><div key={item.id}>
          <strong>{item.name}</strong><span>{item.email}</span>
          <small>Versão {item.terms_version} · Pendente de verificação</small>
        </div>)}
      </div>}
      <p className="enroll-footnote"><ShieldCheck size={16}/>
        Este painel não concede recompensas. Aceites pendentes não entram na lista de participantes
        até a identidade ser verificada na plataforma de origem.</p>
    </div>}
  </section>;
}
