import {useEffect, useState, type FormEvent} from "react";
import {ArrowRight,CheckCircle2, HeartHandshake, LockKeyhole, ShieldCheck,Gift,Mail} from "lucide-react";
import {ApiError, publicEnrollmentApi, type PublicInvitationPreview,
  type PublicConsentResult, type PublicStoreProgram,
  type PublicStoreJoinResult} from "./api";
import {readableForeground} from "./brand-contrast";
import "./public-enrollment.css";

function getToken(){
  const fragment=window.location.hash.startsWith("#")
    ? window.location.hash.slice(1):"";
  return new URLSearchParams(fragment).get("convite")||"";
}

export default function PublicEnrollment(){
  const [token]=useState(getToken);
  const [storeSlug]=useState(()=>{
    const match=window.location.pathname.match(/^\/participar\/([a-z0-9-]+)\/?$/i);
    return match?match[1]:"";
  });
  const [preview,setPreview]=useState<PublicInvitationPreview|PublicStoreProgram|null>(null);
  const [result,setResult]=useState<PublicConsentResult|PublicStoreJoinResult|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [name,setName]=useState("");
  const [email,setEmail]=useState("");
  const [accepted,setAccepted]=useState(false);
  const [marketing,setMarketing]=useState(false);

  useEffect(()=>{
    let active=true;
    if(!token&&!storeSlug){
      setError("Informe um link de convite ou uma página específica de loja.");
      setLoading(false);return;
    }
    publicEnrollmentApi.prepareCsrf()
      .then(async ()=>{
        if(storeSlug) return await publicEnrollmentApi.store(storeSlug);
        return await publicEnrollmentApi.preview(token);
      })
      .then(data=>{if(active){setPreview(data);setError("");}})
      .catch(cause=>{if(active)setError(
        cause instanceof ApiError?cause.message:"Não foi possível validar o convite."
      )})
      .finally(()=>{if(active)setLoading(false)});
    return ()=>{active=false};
  },[token,storeSlug]);

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(!preview||!accepted||busy)return;
    setBusy(true);setError("");
    try{
      const values={
        name:name.trim(),email:email.trim(),accepted_terms:accepted,
        marketing_opt_in:marketing
      };
      const receipt=storeSlug
        ?await publicEnrollmentApi.joinStore(storeSlug,{
          ...values,terms_version:preview.terms.version
        })
        :await publicEnrollmentApi.accept({token,...values});
      setResult(receipt);setPreview(null);
      window.history.replaceState(null,"",window.location.pathname);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível registrar seu aceite.");
    }finally{setBusy(false);}
  };

  const branding=preview&&"store_slug" in preview?preview.branding:null;
  const primary=branding?.primary_color||"#087F79";
  const accent=branding?.accent_color||"#37D5BB";
  const publicTitle=branding?.program_name||preview?.store_name||"FIDELIZA";

  return <div className="public-enroll-shell">
    <main className="public-enroll-card">
      <div className="public-enroll-brand"><span style={{background:accent,color:readableForeground(accent)}}><HeartHandshake size={25}/></span>
        <div><strong>{publicTitle}</strong><small>Seu clube de vantagens</small></div></div>
      {loading && <div role="status" className="public-enroll-state">Validando convite seguro…</div>}
      {!loading && result && <div className="public-enroll-done" role="status">
        <CheckCircle2 size={42}/>
        <h1>Quase lá! Sua adesão foi registrada.</h1>
        <p>Recebemos sua solicitação de participação e o aceite do regulamento versão {result.terms_version}.</p>
        <p><strong>Confira seu e-mail para confirmar o cadastro.</strong>
          A confirmação e o vínculo à loja são necessários para participar.
          Nenhum ponto ou desconto é concedido no cadastro.</p>
        {"receipt_id" in result && <span>Protocolo de aceite: {result.receipt_id}</span>}
      </div>}
      {!loading && !result && <>
        <div className="public-enroll-top"><span className="public-enroll-eyebrow">
          <ShieldCheck size={16}/> ADESÃO VOLUNTÁRIA</span>
          <h1>Entre para o clube de vantagens.</h1>
          <p>{preview
            ? ("store_slug" in preview
                ? "Participe do clube da "+preview.store_name+". É gratuito solicitar a adesão e acompanhar os benefícios divulgados."
                : "Você recebeu um convite da "+preview.store_name+". Confira as regras antes de participar.")
            :"O cadastro público desta loja não está disponível."}</p></div>
        {error && <div role="alert" className="public-enroll-error">{error}</div>}
        {preview && <form onSubmit={submit}>
          <div className="public-enroll-value">
            <Gift size={19}/><span>Confira os benefícios publicados no Meu Clube.
              O acúmulo de pontos e o resgate ainda estão em preparação.</span>
          </div>
          <div className="public-enroll-fields">
            <label>Seu nome
              <input autoComplete="name" required minLength={3} maxLength={140} value={name}
                onChange={e=>setName(e.target.value)} placeholder="Nome completo"/>
            </label>
            <label>Seu e-mail
              <input autoComplete="email" required type="email" maxLength={254} value={email}
                onChange={e=>setEmail(e.target.value)} placeholder="voce@exemplo.com"/>
            </label>
          </div>
          <div className="public-enroll-policies">
            <details className="public-enroll-terms">
              <summary>Ler regulamento · {preview.terms.title} · versão {preview.terms.version}</summary>
              <p>{preview.terms.body}</p>
            </details>
            {preview.terms.privacy_notice&&<details className="public-enroll-terms public-enroll-privacy">
              <summary>Ler aviso de privacidade</summary>
              <p>{preview.terms.privacy_notice}</p>
            </details>}
          </div>
          <label className="public-enroll-choice">
            <input type="checkbox" required checked={accepted}
              onChange={e=>setAccepted(e.target.checked)}/>
            <span>Li e aceito o <strong>regulamento do clube</strong> e estou ciente do aviso de privacidade. A adesão depende de confirmação.</span>
          </label>
          <label className="public-enroll-choice">
            <input type="checkbox" checked={marketing}
              onChange={e=>setMarketing(e.target.checked)}/>
            <span>Também aceito receber comunicações promocionais. Esta escolha é opcional e independente da adesão.</span>
          </label>
          <button className="public-enroll-submit" type="submit" style={{background:primary,color:readableForeground(primary)}} disabled={!accepted||busy}>
            {busy?"Registrando…":"Quero participar"} <ArrowRight size={17}/>
          </button>
          <div className="public-enroll-warning"><LockKeyhole size={16}/>
            Confirmação por e-mail e proteção dos seus dados. Nenhum benefício é
            gerado antes da ativação do programa.</div>
        </form>}
      </>}
      {storeSlug&&<p className="public-enroll-privacy-link">
        <a href={"/clube/"+encodeURIComponent(storeSlug)}><Mail size={15}/> Conhecer Meu Clube ou entrar com meu e-mail</a>
      </p>}
      {branding?.support_email&&<p className="public-enroll-privacy-link">
        Dúvidas sobre o programa? <a href={"mailto:"+branding.support_email}>
          {branding.support_email}</a>
      </p>}
      {storeSlug && <p className="public-enroll-privacy-link">
        Quer retirar sua solicitação de adesão?
        <a href={"/retirar/"+encodeURIComponent(storeSlug)}>Solicitar retirada por e-mail</a>.
      </p>}
    </main>
    <footer>Vidalys Fideliza · Sem inscrição automática · Seus dados são usados para registrar esta solicitação.</footer>
  </div>;
}
