import {useEffect, useState, type FormEvent} from "react";
import {ArrowRight, BadgeCheck, BookOpen, CheckCircle2, Clock3, Gift, HeartHandshake, LockKeyhole, Mail, ShieldCheck} from "lucide-react";
import {ApiError, publicEnrollmentApi, type MemberClubPublic, type MemberClubPrivate} from "./api";
import {readableForeground} from "./brand-contrast";
import "./member-club.css";

const slug = decodeURIComponent(window.location.pathname.match(/^\/clube\/([a-z0-9-]+)\/?$/i)?.[1] || "");

export default function MemberClub(){
  const [token] = useState(()=>
    new URLSearchParams(window.location.hash.replace(/^#/,"")).get("acesso") || "");
  const [club,setClub] = useState<MemberClubPublic|null>(null);
  const [me,setMe] = useState<MemberClubPrivate|null>(null);
  const [loading,setLoading] = useState(true);
  const [ready,setReady] = useState(false);
  const [email,setEmail] = useState("");
  const [busy,setBusy] = useState(false);
  const [sent,setSent] = useState(false);
  const [error,setError] = useState("");

  useEffect(()=>{
    if(token)window.history.replaceState(null,"",window.location.pathname);
    let mounted=true;
    Promise.all([
      publicEnrollmentApi.club(slug),
      publicEnrollmentApi.prepareCsrf(),
    ]).then(async ([info])=>{
      if(!mounted)return;
      setClub(info);setReady(true);
      if(!token){
        try {
          const account=await publicEnrollmentApi.clubMe(slug);
          if(mounted)setMe(account);
        } catch(e) {
          if(mounted && (!(e instanceof ApiError) || (e.status!==401 && e.status!==403)))
            setError("Não foi possível consultar seu acesso. Tente novamente.");
        }
      }
    }).catch(()=>{
      if(mounted)setError("Não foi possível carregar o clube. Verifique a conexão.");
    }).finally(()=>{if(mounted)setLoading(false)});
    return ()=>{mounted=false};
  },[token]);

  const requestAccess=async(e:FormEvent)=>{
    e.preventDefault();if(busy||!ready)return;
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.clubRequestAccess(slug,email.trim());
      setEmail("");setSent(true);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Falha ao solicitar seu acesso.");
    }finally{setBusy(false)}
  };

  const confirm=async()=>{
    if(!ready||busy||!token)return;
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.clubConfirmAccess(slug,token);
      const account=await publicEnrollmentApi.clubMe(slug);
      setMe(account);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Este link não pôde ser confirmado.");
    }finally{setBusy(false)}
  };

  const logout=async()=>{
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.clubLogout(slug);
      setMe(null);setSent(false);
    }catch{setError("Não foi possível encerrar o acesso.");}
    finally{setBusy(false)}
  };

  const color=club?.branding.primary_color || "#087F79";
  const accent=club?.branding.accent_color || "#37D5BB";
  const program=club?.branding.program_name || (club ? "Clube "+club.store_name : "Meu Clube");
  const firstName=me?.display_name.split(" ")[0] || "participante";
  const state=me?.status==="active"?"Participando":me?.status==="paused"?"Pausado":"Aguardando vínculo";

  return <div className="member-club-shell">
    <header className="member-club-top">
      <div className="member-club-mark" style={{background:accent,color:readableForeground(accent)}}>
        <HeartHandshake size={23}/>
      </div>
      <div className="member-club-brand">
        <strong>{program}</strong><small>TECNOLOGIA VIDALYS FIDELIZA</small>
      </div>
      {me&&<button className="member-club-logout" type="button" disabled={busy} onClick={()=>void logout()}>
        Sair do clube
      </button>}
    </header>
    <main className="member-club-main">
      {loading&&<div className="member-club-panel" role="status">Carregando o clube…</div>}
      {error&&<div className="member-club-error" role="alert">{error}</div>}
      {!loading&&club&&!me&&<div className="member-club-guest">
        <section className="member-club-hero" style={{background:color,color:readableForeground(color)}}>
          <span className="member-club-eyebrow"><Gift size={16}/> SEU CLUBE DE VANTAGENS</span>
          <h1>Bem-vindo ao {program}.</h1>
          <p>Um lugar para acompanhar sua participação, entender as regras e, quando a loja liberar, consultar seus pontos e recompensas.</p>
          <span className="member-club-hero-note"><ShieldCheck size={16}/> Seus dados só aparecem após confirmação por e-mail.</span>
        </section>
        <section className="member-club-panel" aria-label="Entrar no clube">
          {token?<div className="member-club-access">
            <LockKeyhole size={26}/>
            <h2>Confirme seu acesso</h2>
            <p>Este link pessoal é de uso único e expira em 15 minutos.</p>
            <button type="button" className="member-club-button" disabled={!ready||busy}
              onClick={()=>void confirm()}>{busy?"Confirmando…":"Confirmar e entrar"} <ArrowRight size={17}/></button>
          </div>:sent?<div className="member-club-access" role="status">
            <Mail size={29}/><h2>Confira seu e-mail</h2>
            <p>Se existir uma adesão com e-mail confirmado, enviaremos um link de acesso privado. Confira também a caixa de spam.</p>
            <button type="button" className="member-club-light" onClick={()=>setSent(false)}>Usar outro e-mail</button>
          </div>:<>
            <span className="member-club-kicker"><LockKeyhole size={16}/> ACESSO DO PARTICIPANTE</span>
            <h2>Entre no seu clube</h2>
            <p>Não precisa criar senha. Enviaremos um link temporário ao e-mail confirmado na adesão.</p>
            <form onSubmit={requestAccess} className="member-club-login">
              <label htmlFor="member-club-email">Seu e-mail</label>
              <input id="member-club-email" type="email" required autoComplete="email"
                maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}
                placeholder="voce@exemplo.com"/>
              <button className="member-club-button" type="submit" disabled={!ready||busy}>
                {busy?"Solicitando…":"Enviar link de acesso"} <ArrowRight size={17}/>
              </button>
            </form>
            {club.signup_available&&<p className="member-club-join">Ainda não participa?
              <a href={"/participar/"+encodeURIComponent(slug)}> Fazer adesão</a>
            </p>}
          </>}
        </section>
      </div>}
      {!loading&&me&&<div className="member-club-account">
        <section className="member-club-hero" style={{background:color,color:readableForeground(color)}}>
          <span className="member-club-eyebrow"><BadgeCheck size={16}/> MINHA PARTICIPAÇÃO</span>
          <h1>Olá, {firstName}.</h1>
          <p>Este é seu espaço para acompanhar seu clube.</p>
          <span className="member-club-hero-note"><CheckCircle2 size={16}/> Situação: {state}</span>
        </section>
        <div className="member-club-summary">
          <section className="member-club-panel">
            <span className="member-club-kicker"><Gift size={17}/> MEUS PONTOS</span>
            <strong className="member-club-big-number">—</strong>
            <p>O programa de pontos ainda não está ativo. Nenhum saldo foi atribuído a este cadastro.</p>
          </section>
          <section className="member-club-panel">
            <span className="member-club-kicker"><Clock3 size={17}/> RECOMPENSAS</span>
            <h2>Ainda não disponíveis</h2>
            <p>Quando a loja publicar regras e recompensas, você verá aqui as opções reais de resgate.</p>
          </section>
        </div>
        <section className="member-club-panel">
          <span className="member-club-kicker"><BookOpen size={16}/> REGRAS DO CLUBE</span>
          <h2>{me.terms.title}</h2>
          <p>Versão aceita: {me.terms.version}</p>
          <details className="member-club-terms"><summary>Ler regulamento completo</summary>
            <p>{me.terms.body}</p>
          </details>
          {me.terms.privacy_notice&&<details className="member-club-terms"><summary>Meu aviso de privacidade</summary>
            <p>{me.terms.privacy_notice}</p>
          </details>}
        </section>
        <section className="member-club-panel">
          <span className="member-club-kicker"><ShieldCheck size={16}/> HISTÓRICO</span>
          <h2>Sem movimentações de pontos</h2>
          <p>Compras pagas, pontos pendentes, liberação e resgates aparecerão aqui quando o motor for implementado e validado. Não exibimos saldos fictícios.</p>
        </section>
      </div>}
      {!loading&&club&&!me&&<section className="member-club-panel member-club-info">
        <span className="member-club-kicker"><BookOpen size={16}/> COMO FUNCIONA</span>
        <h2>Suas vantagens em um só lugar</h2>
        <div className="member-club-steps"><div><strong>01 · Participe</strong><p>Leia e aceite o regulamento e confirme seu e-mail.</p></div>
          <div><strong>02 · Compre</strong><p>Quando o programa estiver ativo, compras elegíveis e pagas serão verificadas.</p></div>
          <div><strong>03 · Acompanhe</strong><p>Pontos e resgates futuros terão histórico e regras transparentes.</p></div></div>
        {club.terms&&<details className="member-club-terms"><summary>Conhecer o regulamento</summary><p>{club.terms.body}</p></details>}
      </section>}
      {club?.branding.support_email&&<p className="member-club-support">Dúvidas sobre o clube?
        <a href={"mailto:"+club.branding.support_email}> Fale com a loja</a>
      </p>}
    </main>
    <footer className="member-club-footer"><LockKeyhole size={13}/> Vidalys Fideliza · Clube independente da plataforma de vendas</footer>
  </div>;
}
