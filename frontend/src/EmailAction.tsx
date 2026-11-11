import {useEffect, useState} from "react";
import {CheckCircle2, HeartHandshake, LockKeyhole, ShieldCheck} from "lucide-react";
import {ApiError, publicEnrollmentApi, type EmailActionResult} from "./api";
import "./public-enrollment.css";

export default function EmailAction(){
  const [link]=useState(()=>{
    const hash=new URLSearchParams(window.location.hash.replace(/^#/,""));
    const action=hash.get("acao");
    return {action:action==="verify"||action==="withdraw"?action:null,
      token:hash.get("token")||""};
  });
  const [ready,setReady]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [result,setResult]=useState<EmailActionResult|null>(null);
  const isValid=link.action!==null&&/^[A-Za-z0-9_-]{32,128}$/.test(link.token);

  useEffect(()=>{
    let active=true;
    if(!isValid){setError("Link de confirmação inválido.");return;}
    publicEnrollmentApi.prepareCsrf()
      .then(()=>{if(active)setReady(true);})
      .catch(()=>{if(active)setError("Não foi possível iniciar uma sessão segura.");});
    return ()=>{active=false;};
  },[isValid]);

  const confirm=async()=>{
    if(!isValid||!link.action||busy)return;
    setError("");setBusy(true);
    try{
      const response=await publicEnrollmentApi.confirmEmailAction(link.token,link.action as "verify"|"withdraw");
      setResult(response);
      window.history.replaceState(null,"",window.location.pathname);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível confirmar.");
    }finally{setBusy(false);}
  };
  const withdrawing=link.action==="withdraw";

  return <div className="public-enroll-shell">
    <main className="public-enroll-card">
      <div className="public-enroll-brand"><span><HeartHandshake size={25}/></span>
        <div><strong>VIDALYS FIDELIZA</strong><small>SEGURANÇA E PRIVACIDADE</small></div></div>
      {result ? <div className="public-enroll-done" role="status">
        <CheckCircle2 size={42}/>
        <h1>{withdrawing?"Solicitação retirada.":"E-mail confirmado."}</h1>
        <p>{result.message}</p>
        <p>Este processo não concedeu cashback, pontos ou descontos.</p>
      </div> : <>
        <div className="public-enroll-top">
          <span className="public-enroll-eyebrow"><ShieldCheck size={16}/> ETAPA DE SEGURANÇA</span>
          <h1>{withdrawing?"Deseja retirar sua solicitação?":"Confirme seu endereço de e-mail"}</h1>
          <p>{withdrawing
            ?"Confirmando, a solicitação será encerrada e não será promovida a participante ativo."
            :"Esta etapa confirma o acesso ao e-mail. A validação como cliente da loja será feita separadamente."}</p>
        </div>
        {error && <div role="alert" className="public-enroll-error">{error}</div>}
        {isValid && <button type="button" className="public-enroll-submit"
          onClick={()=>void confirm()} disabled={!ready||busy}>
          {busy?"Confirmando…":withdrawing?"Confirmar retirada":"Confirmar meu e-mail"}
        </button>}
        <div className="public-enroll-warning"><LockKeyhole size={17}/>
          O link expira em 30 minutos, é de uso único e não ativa benefícios.
        </div>
      </>}
    </main>
    <footer>Tecnologia Vidalys · Solicitações de adesão seguras</footer>
  </div>;
}
