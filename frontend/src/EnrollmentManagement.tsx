import {useEffect, useState, type FormEvent} from "react";
import {ApiError, merchantApi, type CustomerMatchPreview, type EnrollmentPendingList, type ProgramTerms, type Store} from "./api";
import {ArrowRight, Check, ClipboardCopy, FileCheck2, HeartHandshake, Link2, ShieldCheck} from "lucide-react";
import "./enrollment.css";

export default function EnrollmentManagement({
  tenantId, role, storeSlug, tenantStatus
}:{tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"]}){
  const [terms,setTerms]=useState<ProgramTerms|null>(null);
  const [pending,setPending]=useState<EnrollmentPendingList|null>(null);
  const [loading,setLoading]=useState(true);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [formOpen,setFormOpen]=useState(false);
  const [version,setVersion]=useState("v1");
  const [title,setTitle]=useState("Regulamento do programa de fidelidade");
  const [body,setBody]=useState("");
  const [privacy,setPrivacy]=useState("");
  const [signupEnabled,setSignupEnabled]=useState(false);
  const [customerAccess,setCustomerAccess]=useState(false);
  const [customerCheckBusy,setCustomerCheckBusy]=useState<string|null>(null);
  const [customerCheckResult,setCustomerCheckResult]=useState<{
    submissionId:string;status:CustomerMatchPreview["status"];customerId:string|null
  }|null>(null);
  const [customerCheckError,setCustomerCheckError]=useState("");
  const [busy,setBusy]=useState(false);
  const [link,setLink]=useState("");
  const [copied,setCopied]=useState(false);
  const canEdit=role==="owner"||role==="admin";
  const publicReady=signupEnabled&&tenantStatus==="active"&&Boolean(terms?.privacy_notice?.trim().length&&terms.privacy_notice.trim().length>=120)&&!formOpen;
  const publicUrl=window.location.origin+"/participar/"+encodeURIComponent(storeSlug);

  useEffect(()=>{
    if(!canEdit){setLoading(false);return;}
    let active=true;setLoading(true);setError("");setLink("");
    setCustomerAccess(false);setCustomerCheckResult(null);setCustomerCheckError("");
    merchantApi.nuvemshopStatus(tenantId)
      .then(n=>{if(active)setCustomerAccess(Boolean(n.customer_matching?.read_only_preview_available));})
      .catch(()=>{if(active)setCustomerAccess(false)});
    Promise.all([
      merchantApi.currentProgramTerms(tenantId),
      merchantApi.pendingEnrollments(tenantId)
    ]).then(([t,p])=>{
      if(!active)return;
      setTerms(t.terms);setPending(p);setSignupEnabled(t.public_signup_enabled);
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
        version:version.trim(),title:title.trim(),body:body.trim(),
        privacy_notice:privacy.trim()
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
    setFormOpen(true);setVersion("");setBody("");setPrivacy("");setLink("");setMessage("");
  };
  const previewCustomer=async(submissionId:string)=>{
    setCustomerCheckBusy(submissionId);setCustomerCheckError("");setCustomerCheckResult(null);
    try{
      const result=await merchantApi.previewCustomerMatch(tenantId,submissionId);
      setCustomerCheckResult({submissionId,status:result.status,customerId:result.customer_id});
    }catch(cause){
      setCustomerCheckError(cause instanceof ApiError?cause.message:"Falha na prévia autorizada.");
    }finally{setCustomerCheckBusy(null);}
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
        <label>Aviso de privacidade da loja (separado do regulamento)
          <textarea required minLength={120} maxLength={2500} rows={5} value={privacy}
            placeholder="Informe o responsável pelos dados, finalidade, forma de contato, direitos do titular e prazo de retenção."
            onChange={e=>setPrivacy(e.target.value)}/>
        </label>
        <p className="enroll-muted">O texto e o aviso de privacidade devem ser revisados antes da divulgação.
          A nova versão invalida convites antigos ainda não aceitos.</p>
        <div className="enroll-actions">
          {terms && <button type="button" className="enroll-secondary"
            onClick={()=>setFormOpen(false)}>Cancelar</button>}
          <button type="submit" className="portal-primary" disabled={busy||body.trim().length<80||privacy.trim().length<120}>
            <FileCheck2 size={17}/>{busy?"Registrando…":"Aprovar esta versão"}
          </button>
        </div>
      </form>}
      <div className="enroll-step">
        <span className="enroll-step-number">02</span>
        <div><strong>Página pública da loja</strong>
          <p>{publicReady?"Link permanente para solicitar adesão com seus termos e aviso de privacidade."
            :!signupEnabled?"Adesão pública bloqueada até aprovação técnica e jurídica."
            :"Disponível quando a loja estiver ativa e tiver termos e privacidade aprovados."}</p>
        </div>
      </div>
      {publicReady && <div className="enroll-share">
        <label>Link para divulgar na loja ou compartilhar
          <input readOnly value={publicUrl} onFocus={e=>e.target.select()}/>
        </label>
        <button type="button" className="enroll-secondary"
          onClick={()=>void navigator.clipboard.writeText(publicUrl).then(()=>{
            setMessage("Link público copiado para compartilhar.");
          }).catch(()=>setError("Selecione e copie o link manualmente."))}>
          <ClipboardCopy size={16}/> Copiar página
        </button>
      </div>}
      <div className="enroll-step">
        <span className="enroll-step-number">03</span>
        <div><strong>Convite individual de adesão</strong>
          <p>Link único, válido por 24 horas. Envie manualmente, somente com a autorização necessária.</p>
        </div>
        <button type="button" disabled={!signupEnabled||!terms||formOpen||busy} className="enroll-secondary"
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
        <span className="enroll-step-number">04</span>
        <div><strong>Aceites aguardando verificação</strong>
          <p>{pending?pending.total+" aceite(s) registrado(s) sem vínculo de cliente confirmado."
            :"Os aceites serão exibidos aqui depois de recebidos."}</p>
        </div>
        <ArrowRight size={18} aria-hidden="true"/>
      </div>
      {pending?.items.some(item=>item.status==="email_verified") && !customerAccess &&
        <p className="enroll-muted">Vínculo com clientes da Nuvemshop indisponível.
          A etapa requer autorização de leitura de clientes (<code>read_customers</code>) no aplicativo,
          reinstalação na loja e liberação da prévia na homologação.</p>}
      {customerCheckError && <div className="enroll-error" role="alert">{customerCheckError}</div>}
      {pending && pending.items.length>0 && <div className="enroll-pending-list">
        {pending.items.map(item=><div key={item.id}>
          <strong>{item.name}</strong><span>{item.email}</span>
          <small>Versão {item.terms_version} · {item.status==="email_verified"
            ?"E-mail confirmado · aguardando vínculo com a loja"
            :"Aguardando confirmação do e-mail"}</small>
          {item.status==="email_verified" && customerAccess && <div className="enroll-match-action">
            <button type="button" className="enroll-secondary"
              disabled={customerCheckBusy!==null}
              onClick={()=>void previewCustomer(item.id)}>
              {customerCheckBusy===item.id?"Consultando…":"Conferir cadastro na Nuvemshop"}
            </button>
            <span>Somente prévia. Nenhum participante ou benefício será criado.</span>
          </div>}
          {customerCheckResult?.submissionId===item.id && <div className="enroll-match-result"
            role="status">
            {customerCheckResult.status==="one_exact_match"
              ?"Correspondência exata: cliente nº "+customerCheckResult.customerId+
                " — ainda precisa de aprovação e vínculo seguro."
              :customerCheckResult.status==="ambiguous"
                ?"Mais de um cadastro correspondente; não é seguro vincular automaticamente."
                :"Nenhum cadastro correspondente encontrado nesta loja."}
          </div>}
        </div>)}
      </div>}
      <p className="enroll-footnote"><ShieldCheck size={16}/>
        Este painel não concede recompensas. Aceites pendentes não entram na lista de participantes
        até a identidade ser verificada na plataforma de origem.</p>
    </div>}
  </section>;
}
