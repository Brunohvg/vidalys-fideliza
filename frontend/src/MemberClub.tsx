import {useEffect, useState, type FormEvent} from "react";
import {ArrowRight, BadgeCheck, BookOpen, CheckCircle2, Clock3, Gift, HeartHandshake, LockKeyhole, Mail, ShieldCheck, TicketPercent, ShoppingBag, LogOut} from "lucide-react";
import {ApiError, publicEnrollmentApi, type MemberClubPublic, type MemberClubPrivate} from "./api";
import {readableForeground} from "./brand-contrast";
import "./member-club.css";

const slug = decodeURIComponent(window.location.pathname.match(/^\/clube\/([a-z0-9-]+)\/?$/i)?.[1] || "");
const money=(cents:number)=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(cents/100);

export default function MemberClub(){
  const [token,setToken] = useState(()=>
    new URLSearchParams(window.location.hash.replace(/^#/,"")).get("acesso") || "");
  const [club,setClub] = useState<MemberClubPublic|null>(null);
  const [me,setMe] = useState<MemberClubPrivate|null>(null);
  const [loading,setLoading] = useState(true);
  const [ready,setReady] = useState(false);
  const [email,setEmail] = useState("");
  const [busy,setBusy] = useState(false);
  const [sent,setSent] = useState(false);
  const [error,setError] = useState("");
  const [section,setSection] = useState<"rewards"|"history"|"rules">("rewards");

  useEffect(()=>{
    // Links recebidos no mesmo navegador também precisam ser reconhecidos,
    // inclusive quando o SPA já está aberto nesta rota.
    const readIncomingLink = () => {
      const next = new URLSearchParams(window.location.hash.replace(/^#/,""))
        .get("acesso") || "";
      if(next){
        setMe(null);
        setSent(false);
        setError("");
        setToken(next);
      }
    };
    window.addEventListener("hashchange", readIncomingLink);
    return ()=>window.removeEventListener("hashchange", readIncomingLink);
  },[]);

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
  const state=me?.status==="active"?"Participando":me?.status==="paused"?"Pausado":"Aguardando ativação";
  const pointsReady=me?.points_status==="verified"&&typeof me.points_balance==="number";
  const availablePoints=pointsReady?me.points_balance:null;
  const publishedRewards=me?.available_rewards || [];
  const nextReward=publishedRewards
    .filter(item=>item.status!=="paused"&&item.status!=="sold_out"&&item.points_cost>0)
    .sort((a,b)=>a.points_cost-b.points_cost)[0];
  const nextProgress=availablePoints!==null&&nextReward
    ?Math.min(100,Math.round(availablePoints/nextReward.points_cost*100)):null;

  return <div className="member-club-shell">
    <header className="member-club-top">
      <div className="member-club-mark" style={{background:accent,color:readableForeground(accent)}}>
        <HeartHandshake size={23}/>
      </div>
      <div className="member-club-brand">
        <strong>{program}</strong><small>TECNOLOGIA VIDALYS FIDELIZA</small>
      </div>
      {me&&<button className="member-club-logout" type="button" disabled={busy} onClick={()=>void logout()}>
        <LogOut size={16} aria-hidden="true"/><span className="member-club-logout-desktop">Sair do clube</span>
        <span className="member-club-logout-mobile">Sair</span>
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
        <section className="member-club-hero member-club-hero-account"
          style={{background:color,color:readableForeground(color)}}>
          <span className="member-club-eyebrow"><BadgeCheck size={15}/> SEU CLUBE DE VANTAGENS</span>
          <h1>Olá, {firstName}!</h1>
          <span className="member-club-hero-note"><CheckCircle2 size={15}/> {state}</span>
        </section>
        <section className="member-club-wallet member-club-panel" aria-label="Resumo da minha carteira">
          <div className="member-club-wallet-main">
            <span className="member-club-kicker"><Gift size={16}/> MEUS PONTOS</span>
            <span className="member-club-wallet-label">Pontos disponíveis</span>
            <strong className="member-club-wallet-number">
              {availablePoints!==null?availablePoints.toLocaleString("pt-BR"):"—"}
            </strong>
            <p>{pointsReady
              ?"Veja abaixo quais recompensas você pode conquistar."
              :"O clube ainda não liberou a pontuação. Nenhum saldo foi atribuído."}</p>
          </div>
          {pointsReady&&<div className="member-club-wallet-aside">
            <div><Clock3 size={18}/><span>Pendentes</span>
              <strong>{me.points_pending!==null?me.points_pending.toLocaleString("pt-BR"):"—"}</strong>
            </div>
            <div><Gift size={18}/><span>A vencer</span>
              <strong>{me.points_expiring!==null?me.points_expiring.toLocaleString("pt-BR"):"—"}</strong>
            </div>
          </div>}
        </section>
        <nav className="member-club-sections" aria-label="Seu clube">
          <button type="button" aria-pressed={section==="rewards"}
            className={section==="rewards"?"selected":""}
            onClick={()=>setSection("rewards")}>
            <Gift size={16}/> Recompensas
          </button>
          <button type="button" aria-pressed={section==="history"}
            className={section==="history"?"selected":""}
            onClick={()=>setSection("history")}>
            <Clock3 size={16}/> Histórico
          </button>
          <button type="button" aria-pressed={section==="rules"}
            className={section==="rules"?"selected":""}
            onClick={()=>setSection("rules")}>
            <BookOpen size={16}/> Regras
          </button>
        </nav>
        {section==="rewards"&&<section className="member-club-panel member-club-rewards"
          aria-labelledby="member-rewards-title">
          <span className="member-club-kicker"><TicketPercent size={16}/> SEUS BENEFÍCIOS</span>
          <h2 id="member-rewards-title">Recompensas do clube</h2>
          {nextReward&&nextProgress!==null&&<div className="member-club-next">
            <div className="member-club-next-heading">
              <span>Seu próximo benefício</span>
              <strong>{money(nextReward.discount_cents)} de desconto</strong>
            </div>
            <div className="member-club-progress" role="progressbar"
              aria-label="Progresso para próxima recompensa" aria-valuemin={0}
              aria-valuemax={nextReward.points_cost}
              aria-valuenow={Math.min(availablePoints??0,nextReward.points_cost)}>
              <span style={{width:nextProgress+"%"}}/>
            </div>
            <small>{availablePoints!==null&&availablePoints>=nextReward.points_cost
              ?"Você já tem pontos suficientes. Aguarde a liberação do resgate."
              :"Faltam "+Math.max(0,nextReward.points_cost-(availablePoints??0)).toLocaleString("pt-BR")+" pontos."}</small>
          </div>}
          {publishedRewards.length===0?<div className="member-club-rewards-empty">
            <span><Gift size={24}/></span>
            <div><h3>Recompensas em preparação</h3>
              <p>A loja ainda não publicou descontos para resgatar.</p>
            </div>
          </div>:<div className="member-club-rewards-grid">
            {publishedRewards.map(reward=><article className="member-club-reward" key={reward.id}>
              <span className="member-club-reward-symbol"><TicketPercent size={21}/></span>
              <h3>{reward.title}</h3>
              <strong>{money(reward.discount_cents)} de desconto</strong>
              <p>{reward.points_cost.toLocaleString("pt-BR")} pontos
                <span className="member-club-reward-min"> · Pedido mínimo {money(reward.min_order_cents)}</span>
              </p>
              <div className="member-club-reward-state">
                {reward.status==="paused"?"Temporariamente indisponível":
                  reward.status==="sold_out"?"Esgotada":
                  !pointsReady?"Aguardando ativação":
                  availablePoints!==null&&availablePoints<reward.points_cost
                    ?"Faltam "+(reward.points_cost-availablePoints).toLocaleString("pt-BR")+" pontos":
                  me.redemption_enabled&&reward.redemption_enabled&&me.status==="active"
                    ?"Aguardando confirmação do resgate":"Resgate em preparação"}
              </div>
            </article>)}
          </div>}
          <details className="member-club-more">
            <summary><ShoppingBag size={16}/> Como vou usar meus pontos no site?</summary>
            <div className="member-club-more-body">
              <p>Depois da ativação, você poderá trocar pontos por um desconto na próxima compra. O cupom individual será utilizado no checkout da loja.</p>
              <p>Esse resgate ainda não está disponível. Nenhum cupom foi criado nem ponto consumido.</p>
            </div>
          </details>
        </section>}
        {section==="history"&&<section className="member-club-panel member-club-history"
          aria-labelledby="member-history-title">
          <span className="member-club-kicker"><Clock3 size={16}/> MOVIMENTAÇÕES</span>
          <h2 id="member-history-title">Histórico de pontos</h2>
          {me.transactions.length?<ul className="member-club-movements">
            {me.transactions.map(item=><li key={item.id}>
              <div><strong>{item.description}</strong>
                <small>{new Date(item.created_at).toLocaleString("pt-BR")}</small></div>
              <strong>{item.points_delta>0?"+":""}{item.points_delta.toLocaleString("pt-BR")} pts</strong>
            </li>)}
          </ul>:<div className="member-club-simple-empty">
            <Clock3 size={24}/>
            <p>Ainda não há movimentações. Compras pagas e pontos liberados aparecerão aqui.</p>
          </div>}
        </section>}
        {section==="rules"&&<section className="member-club-panel member-club-rules"
          aria-labelledby="member-rules-title">
          <span className="member-club-kicker"><ShieldCheck size={16}/> SEUS DADOS</span>
          <h2 id="member-rules-title">Regras e privacidade</h2>
          <p>Você aceitou {me.terms.title} · versão {me.terms.version}.</p>
          <details className="member-club-terms"><summary>Ler regulamento completo</summary>
            <p>{me.terms.body}</p>
          </details>
          {me.terms.privacy_notice&&<details className="member-club-terms">
            <summary>Meu aviso de privacidade</summary>
            <p>{me.terms.privacy_notice}</p>
          </details>}
        </section>}
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
