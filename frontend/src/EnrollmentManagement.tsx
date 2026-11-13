import {useEffect, useState, type FormEvent} from "react";
import {ApiError, merchantApi, type CustomerMatchPreview, type EnrollmentPendingList, type ProgramTerms, type Store} from "./api";
import {ArrowRight, Check, ClipboardCopy, FileCheck2, HeartHandshake, Link2, ShieldCheck} from "lucide-react";
import "./enrollment.css";

export default function EnrollmentManagement({
  tenantId, role, storeSlug, tenantStatus, onParticipantApproved
}:{tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"];
  onParticipantApproved?:()=>void}){
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
  const [approvalAvailable,setApprovalAvailable]=useState(false);
  const [automaticLinking,setAutomaticLinking]=useState(false);
  const [activeSection,setActiveSection]=useState<"rules"|"share"|"review">("share");
  const [approving,setApproving]=useState<string|null>(null);
  const [approvalTarget,setApprovalTarget]=useState<string|null>(null);
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
    setCustomerAccess(false);setApprovalAvailable(false);setAutomaticLinking(false);
    setApprovalTarget(null);setCustomerCheckResult(null);setCustomerCheckError("");
    merchantApi.nuvemshopStatus(tenantId)
      .then(n=>{if(active){
        setCustomerAccess(Boolean(n.customer_matching?.read_only_preview_available));
        setApprovalAvailable(Boolean(n.customer_matching?.participant_approval_available));
        setAutomaticLinking(Boolean(n.customer_matching?.automatic_linking_available));
      }})
      .catch(()=>{if(active)setCustomerAccess(false)});
    Promise.all([
      merchantApi.currentProgramTerms(tenantId),
      merchantApi.pendingEnrollments(tenantId)
    ]).then(([t,p])=>{
      if(!active)return;
      setTerms(t.terms);setPending(p);setSignupEnabled(t.public_signup_enabled);
      setFormOpen(!t.terms);
      setActiveSection(t.terms ? "share" : "rules");
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
      setApprovalTarget(null);
    }catch(cause){
      setCustomerCheckError(cause instanceof ApiError?cause.message:"Falha na prévia autorizada.");
    }finally{setCustomerCheckBusy(null);}
  };

  const approveCustomer=async(submissionId:string,customerId:string)=>{
    setApproving(submissionId);setError("");setMessage("");setCustomerCheckError("");
    try{
      const result=await merchantApi.approveCustomerLink(tenantId,submissionId,customerId);
      setPending(old=>old?{...old,total:Math.max(0,old.total-1),
        items:old.items.filter(item=>item.id!==submissionId)}:old);
      setCustomerCheckResult(null);setApprovalTarget(null);
      setMessage(result.message);
      onParticipantApproved?.();
    }catch(cause){
      setCustomerCheckError(cause instanceof ApiError
        ?(cause.status===409?"Não foi possível confirmar este vínculo. Consulte novamente o cadastro da loja.":cause.message)
        :"Não foi possível aprovar a participação.");
      setApprovalTarget(null);
    }finally{setApproving(null);}
  };
  return <section className="enroll-manager" aria-labelledby="enroll-title">
    <div className="enroll-head">
      <div className="enroll-symbol"><HeartHandshake size={23}/></div>
      <div><span className="portal-eyebrow">ADESÃO COM CONSENTIMENTO</span>
        <h2 id="enroll-title">Adesão ao seu clube</h2>
        <p>O cliente autoriza sua participação e confirma o e-mail. A identificação na Nuvemshop é um vínculo separado; comprar não significa aderir automaticamente.</p>
      </div>
    </div>
    {loading && <p className="enroll-muted" role="status">Consultando as regras da loja…</p>}
    {error && <div className="enroll-error" role="alert">{error}</div>}
    {message && <div className="enroll-success" role="status"><Check size={16}/>{message}</div>}
    {!loading && <div className="vf-program-tabs" role="tablist" aria-label="Áreas do programa">
      <button type="button" role="tab" aria-selected={activeSection==="rules"} className={activeSection==="rules"?"is-current":""} onClick={()=>setActiveSection("rules")}><FileCheck2 size={16}/> Regulamento</button>
      <button type="button" role="tab" aria-selected={activeSection==="share"} className={activeSection==="share"?"is-current":""} onClick={()=>setActiveSection("share")}><Link2 size={16}/> Página e convites</button>
      <button type="button" role="tab" aria-selected={activeSection==="review"} className={activeSection==="review"?"is-current":""} onClick={()=>setActiveSection("review")}><ShieldCheck size={16}/> Solicitações {pending?.total ? "("+pending.total+")" : ""}</button>
    </div>}
    {!loading && <div className="enroll-content">
      {activeSection==="rules" && <>
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
      </>}
      {activeSection==="share" && <>
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
      </>}
      {activeSection==="review" && <>
      <div className="enroll-step">
        <span className="enroll-step-number">04</span>
        <div><strong>Aceites aguardando verificação</strong>
          <p>{pending?pending.total+" solicitação(ões) ainda não concluídas."
            :"As solicitações novas aparecerão aqui."}{" "}
            {automaticLinking?"Cadastros com correspondência única são vinculados automaticamente; exceções ficam para revisão."
              :"A equipe da loja revisa apenas os cadastros que ainda não foram vinculados."}</p>
        </div>
        <ArrowRight size={18} aria-hidden="true"/>
      </div>
      {pending?.items.some(item=>item.status==="email_verified") && !customerAccess &&
        <p className="enroll-muted">Ainda não é possível conferir cadastros de clientes.
          Confira a conexão da loja em Configurações para acompanhar quando esta função ficar disponível.</p>}
      {customerCheckError && <div className="enroll-error" role="alert">{customerCheckError}</div>}
      {pending && pending.items.length>0 && <div className="enroll-pending-list">
        {pending.items.map(item=><div key={item.id}>
          <strong>{item.name}</strong><span>{item.email}</span>
          <small>Versão {item.terms_version} · {item.status==="email_verified"
            ?(automaticLinking?"E-mail confirmado · vínculo automático não concluído, revisão disponível"
              :"E-mail confirmado · aguardando vínculo com a loja")
            :"Aguardando confirmação do e-mail"}</small>
          {item.status==="email_verified" && customerAccess && <div className="enroll-match-action">
            <button type="button" className="enroll-secondary"
              disabled={customerCheckBusy!==null}
              onClick={()=>void previewCustomer(item.id)}>
              {customerCheckBusy===item.id?"Consultando…":automaticLinking
                ?"Revisar cadastro na Nuvemshop":"Conferir cadastro na Nuvemshop"}
            </button>
            <span>Confirme o cadastro antes de permitir a participação.</span>
          </div>}
          {customerCheckResult?.submissionId===item.id && <div className="enroll-match-result"
            role="status">
            {customerCheckResult.status==="one_exact_match"
              ?"Encontramos um cadastro correspondente ao e-mail confirmado."
              :customerCheckResult.status==="ambiguous"
                ?"Há mais de um cadastro correspondente. Esta pessoa precisa de uma revisão."
                :"Não encontramos um cadastro correspondente nesta loja."}
            {customerCheckResult.status==="one_exact_match"&&
              approvalAvailable&&customerCheckResult.customerId&&
              <div className="enroll-approval-panel">
                <p>Confirme a participação apenas após revisar a solicitação e o regulamento aceito.
                  Nenhuma recompensa será liberada agora.</p>
                {approvalTarget===item.id
                  ? <div className="enroll-approval-confirm">
                      <strong>Confirmar a adesão deste cliente ao clube?</strong>
                      <button type="button" className="enroll-secondary"
                        disabled={approving===item.id}
                        onClick={()=>setApprovalTarget(null)}>Voltar</button>
                      <button type="button" className="portal-primary"
                        disabled={approving===item.id}
                        onClick={()=>void approveCustomer(item.id,customerCheckResult.customerId!)}>
                        {approving===item.id?"Confirmando…":"Sim, aprovar participação"}
                      </button>
                    </div>
                  : <button type="button" className="enroll-secondary"
                      disabled={approving!==null}
                      onClick={()=>setApprovalTarget(item.id)}>
                      Aprovar participação
                    </button>}
              </div>}
          </div>}
        </div>)}
      </div>}
      <p className="enroll-footnote"><ShieldCheck size={16}/>
        Este painel não concede recompensas. A confirmação do e-mail não prova uma compra nem libera pontos.</p>
      </>}
    </div>}
  </section>;
}
