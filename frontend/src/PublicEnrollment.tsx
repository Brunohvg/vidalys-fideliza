import {useEffect, useState, type FormEvent} from "react";
import {CheckCircle2, HeartHandshake, LockKeyhole, ShieldCheck} from "lucide-react";
import {ApiError, publicEnrollmentApi, type PublicInvitationPreview,
  type PublicConsentResult, type PublicStoreProgram,
  type PublicStoreJoinResult} from "./api";
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
      .then(()=>storeSlug?publicEnrollmentApi.store(storeSlug):publicEnrollmentApi.preview(token))
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

  return <div className="public-enroll-shell">
    <main className="public-enroll-card">
      <div className="public-enroll-brand"><span><HeartHandshake size={25}/></span>
        <div><strong>VIDALYS</strong><small>FIDELIZA • AMBIENTE DE TESTE</small></div></div>
      {loading && <div role="status" className="public-enroll-state">Validando convite seguro…</div>}
      {!loading && result && <div className="public-enroll-done" role="status">
        <CheckCircle2 size={42}/>
        <h1>Aceite registrado.</h1>
        <p>Sua solicitação de adesão foi registrada com a versão {result.terms_version} do regulamento.</p>
        <p><strong>A loja ainda precisa confirmar sua identidade.</strong> Este registro não gera saldo, desconto, pontos ou cashback.</p>
        {"receipt_id" in result && <span>Protocolo de aceite: {result.receipt_id}</span>}
      </div>}
      {!loading && !result && <>
        <div className="public-enroll-top"><span className="public-enroll-eyebrow">
          <ShieldCheck size={16}/> ADESÃO VOLUNTÁRIA</span>
          <h1>Faça parte de uma relação que vale mais.</h1>
          <p>{preview?"Convite enviado por "+preview.store_name+". Leia as condições antes de decidir participar."
            :"Este convite não está disponível."}</p></div>
        {error && <div role="alert" className="public-enroll-error">{error}</div>}
        {preview && <form onSubmit={submit}>
          <section className="public-enroll-terms">
            <div><strong>{preview.terms.title}</strong>
              <span>Versão {preview.terms.version}</span></div>
            <p>{preview.terms.body}</p>
          </section>
          {preview.terms.privacy_notice && <section className="public-enroll-terms public-enroll-privacy">
            <div><strong>Aviso de privacidade da loja</strong><span>Transparência de dados</span></div>
            <p>{preview.terms.privacy_notice}</p>
          </section>}
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
          <label className="public-enroll-choice">
            <input type="checkbox" required checked={accepted}
              onChange={e=>setAccepted(e.target.checked)}/>
            <span>Li e aceito os termos do programa de fidelidade apresentados acima.</span>
          </label>
          <label className="public-enroll-choice">
            <input type="checkbox" checked={marketing}
              onChange={e=>setMarketing(e.target.checked)}/>
            <span>Também aceito receber comunicações promocionais. Esta escolha é opcional e independente da adesão.</span>
          </label>
          <button className="public-enroll-submit" type="submit" disabled={!accepted||busy}>
            {busy?"Registrando aceite…":"Registrar meu aceite"}
          </button>
          <div className="public-enroll-warning"><LockKeyhole size={16}/>
            A confirmação do vínculo como participante depende da verificação do cadastro pela loja.
            Nenhum benefício é concedido nesta etapa.</div>
        </form>}
      </>}
    </main>
    <footer>Vidalys Fideliza · Sem inscrição automática · Seus dados são usados para registrar esta solicitação.</footer>
  </div>;
}
