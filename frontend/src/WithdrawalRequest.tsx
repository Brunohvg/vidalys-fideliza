import {useEffect,useState,type FormEvent} from "react";
import {HeartHandshake,LockKeyhole,ShieldCheck} from "lucide-react";
import {ApiError,publicEnrollmentApi} from "./api";
import "./public-enrollment.css";

export default function WithdrawalRequest(){
  const [slug]=useState(()=>{
    const p=window.location.pathname.match(/^\/retirar\/([a-z0-9-]+)\/?$/i);
    return p?p[1]:"";
  });
  const [email,setEmail]=useState("");
  const [ready,setReady]=useState(false);
  const [busy,setBusy]=useState(false);
  const [submitted,setSubmitted]=useState(false);
  const [error,setError]=useState("");

  useEffect(()=>{
    let active=true;
    publicEnrollmentApi.prepareCsrf().then(()=>{if(active)setReady(true);})
      .catch(()=>{if(active)setError("Não foi possível validar a sessão segura.");});
    return ()=>{active=false};
  },[]);

  const submit=async(e:FormEvent)=>{
    e.preventDefault();if(!slug||busy||!ready)return;
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.requestWithdrawal(slug,email.trim());
      setSubmitted(true);setEmail("");
    }catch(err){setError(err instanceof ApiError?err.message:"Não foi possível solicitar a retirada.")}
    finally{setBusy(false)}
  };
  return <div className="public-enroll-shell">
    <main className="public-enroll-card">
      <div className="public-enroll-brand"><span><HeartHandshake size={25}/></span>
        <div><strong>VIDALYS FIDELIZA</strong><small>PRIVACIDADE E CONTROLE</small></div>
      </div>
      <div className="public-enroll-top">
        <span className="public-enroll-eyebrow"><ShieldCheck size={16}/> SEUS DIREITOS</span>
        <h1>Retirar minha solicitação</h1>
        <p>Você pode solicitar o encerramento da sua adesão. Para sua segurança, a retirada será confirmada por um link enviado ao e-mail cadastrado.</p>
      </div>
      {submitted?<div className="public-enroll-done" role="status">
        <p>Se houver uma solicitação associada a esse endereço, enviaremos um link para confirmar a retirada.</p>
        <p>Confira sua caixa de entrada e spam. O link expira em 30 minutos.</p>
      </div>:<form onSubmit={submit}>
        <div className="public-enroll-fields">
          <label>Seu e-mail
            <input autoComplete="email" type="email" required maxLength={254}
              value={email} onChange={e=>setEmail(e.target.value)}
              placeholder="voce@exemplo.com"/>
          </label>
        </div>
        {error&&<div role="alert" className="public-enroll-error">{error}</div>}
        <button type="submit" className="public-enroll-submit" disabled={!ready||busy||!slug}>
          {busy?"Enviando solicitação…":"Solicitar retirada por e-mail"}
        </button>
      </form>}
      <div className="public-enroll-warning"><LockKeyhole size={17}/>
        Sua identidade é protegida: não informamos se um e-mail possui cadastro.
        A solicitação não afeta pedidos feitos na loja.
      </div>
    </main>
    <footer>Tecnologia Vidalys · Privacidade dos participantes</footer>
  </div>;
}
