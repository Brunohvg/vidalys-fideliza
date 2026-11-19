import {useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode} from "react";
import {formatPhone} from "./phone-mask";
import {ArrowRight, BookOpen, Cake, CalendarDays, CheckCircle2, CircleHelp, Clock3, Download, Gift, House, KeyRound, ListOrdered, LockKeyhole,
  LogOut, Mail, ScanLine, Share, ShieldCheck, Smartphone, Sparkles, Store, TicketPercent, TriangleAlert, UserRound, X} from "lucide-react";
import {ApiError, publicEnrollmentApi, type MemberClubPrivate, type MemberClubPublic, type MemberClubReward, type MemberOffer} from "./api";
import {installState, onInstallChange, promptInstall, setupClubApp, type InstallState} from "./club-app";
import {readableForeground} from "./brand-contrast";
import {clubSectionForPath, clubSectionPath, clubSlugFromPath, type ClubSection} from "./routes";
import {MemberMissions, MemberVipCard} from "./MemberOverview";
import "./member-club.css";

/* Meu Clube — página do cliente, pelo protótipo aprovado (MeuClube + Entrar).
   Um único endereço: /clube/<loja>. Quem não entrou vê como funciona, participa
   ou recebe o link de acesso; quem entrou vê saldo, trocas, extrato e regras.
   Usa o nome e as cores salvos pela loja. Nunca mostra saldo ou prazo inventado:
   sem dado verificado, aparece "—" e o motivo. */

const urlSlug = clubSlugFromPath(window.location.pathname) || "";
const money = (cents:number) => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(cents/100);
const pts = (value:number) => value.toLocaleString("pt-BR");
const shortMoney = (cents:number) => "R$ "+(cents%100===0?String(cents/100):(cents/100).toFixed(2).replace(".",","));
const initials = (name:string) => name.split(/\s+/).filter(Boolean).slice(0,2).map(w=>w[0]).join("").toUpperCase() || "C";
const validHex = (value:string|undefined, fallback:string) => value && /^#[0-9A-Fa-f]{6}$/.test(value) ? value : fallback;
const percent = (value:number) => new Intl.NumberFormat("pt-BR",{maximumFractionDigits:1}).format(value)+"%";

type Earning = NonNullable<MemberClubPublic["earning"]>;
type Mode = "join" | "login";

function earningHeadline(e:Earning|null|undefined){
  if(!e) return "Junte pontos e troque por descontos.";
  return "Ganhe "+percent(e.points/e.per_cents*100)+" de volta em toda compra.";
}
function earningSentence(e:Earning){
  return "A cada "+money(e.per_cents)+" em compras, você ganha "+pts(e.points)+(e.points===1?" ponto":" pontos")+". Cada ponto vale R$ 0,01.";
}
type Gift = Extract<NonNullable<MemberClubPublic["program"]>,{mode:"giftback"}>;
const giftOf = (club:MemberClubPublic):Gift|null => club.program&&club.program.mode==="giftback"?club.program:null;
function giftSentence(g:Gift){
  return `Cada compra devolve ${percent(g.percent_bps/100)} em crédito (até ${money(g.cap_cents)}), para usar em até ${g.validity_days} dias numa compra a partir de ${money(g.min_order_cents)}.`;
}
function spendFor(e:Earning|null|undefined, points:number){
  if(!e||points<=0) return null;
  return Math.ceil(points*e.per_cents/e.points);
}

export default function MemberClub(){
  const [slug,setSlug] = useState(urlSlug);
  const [token,setToken] = useState(()=>new URLSearchParams(window.location.hash.replace(/^#/,"")).get("acesso")||"");
  const [club,setClub] = useState<MemberClubPublic|null>(null);
  const [me,setMe] = useState<MemberClubPrivate|null>(null);
  const [loading,setLoading] = useState(true);
  const [ready,setReady] = useState(false);
  const [error,setError] = useState("");
  const [section,setSection] = useState<ClubSection>(()=>clubSectionForPath(window.location.pathname));

  useEffect(()=>{
    const restore = () => setSection(clubSectionForPath(window.location.pathname));
    const readLink = () => {
      const next = new URLSearchParams(window.location.hash.replace(/^#/,"")).get("acesso")||"";
      if(next){setMe(null);setError("");setToken(next);}
    };
    window.addEventListener("popstate",restore);
    window.addEventListener("hashchange",readLink);
    return ()=>{window.removeEventListener("popstate",restore);window.removeEventListener("hashchange",readLink);};
  },[]);

  useEffect(()=>{
    if(token) window.history.replaceState(null,"",window.location.pathname);
    let mounted = true;
    Promise.all([publicEnrollmentApi.club(slug), publicEnrollmentApi.prepareCsrf()]).then(async ([info])=>{
      if(!mounted) return;
      // Endereço antigo: a loja trocou o link. Mostra o endereço atual na barra.
      if(info.store_slug && info.store_slug!==slug){
        const path = window.location.pathname.replace("/clube/"+slug,"/clube/"+info.store_slug);
        window.history.replaceState(null,"",path+window.location.hash);
        setSlug(info.store_slug);
      }
      setClub(info);setReady(true);
      if(!token){
        try{
          const account = await publicEnrollmentApi.clubMe(info.store_slug||slug);
          if(mounted) setMe(account);
        }catch(e){
          if(mounted && (!(e instanceof ApiError) || (e.status!==401 && e.status!==403)))
            setError("Não foi possível consultar seu acesso. Tente novamente.");
        }
      }
    }).catch(()=>{if(mounted) setError("Não foi possível carregar o clube. Confira o endereço e a conexão.");})
      .finally(()=>{if(mounted) setLoading(false);});
    return ()=>{mounted=false};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[token]);

  const openSection = (next:ClubSection) => {
    setSection(next);
    const url = clubSectionPath(slug,next);
    if(window.location.pathname!==url) window.history.pushState(null,"",url);
    window.scrollTo({top:0});
  };
  const logout = async () => {
    setError("");
    try{await publicEnrollmentApi.clubLogout(slug);setMe(null);openSection("home");}
    catch{setError("Não foi possível sair agora. Tente novamente.");}
  };

  const brand = validHex(club?.branding.primary_color,"#6A3DF0");
  const accent = validHex(club?.branding.accent_color,"#FFC857");
  const brandInk = readableForeground(brand);
  const style = {
    "--clb-brand":brand, "--clb-brand-ink":brandInk,
    "--clb-brand-end":brandInk==="#FFFFFF"?"color-mix(in srgb, "+brand+" 58%, #24113F)":"color-mix(in srgb, "+brand+" 72%, #FFFFFF)",
    "--clb-accent":accent, "--clb-accent-ink":readableForeground(accent),
  } as CSSProperties;
  const program = club?.branding.program_name || (club ? "Clube "+club.store_name : "Meu Clube");
  useEffect(()=>{if(club) setupClubApp(slug,brand);},[club,slug,brand]);
  const support = club?.branding.support_email || "";

  return <div className={"clb-shell"+(me?" is-member":"")} style={style}>
    <header className="clb-top">
      <span className="clb-store-tile" aria-hidden="true">{initials(club?.store_name||"")}</span>
      <div className="clb-top-text">
        <strong>{program}</strong>
        <span>{me?"Olá, "+(me.display_name.split(" ")[0]||"cliente"):club?club.store_name:"Carregando…"}</span>
      </div>
      {me&&<button type="button" className={"clb-icon-btn"+(section==="profile"?" is-on":"")} aria-label="Meu perfil"
        onClick={()=>openSection("profile")}><UserRound size={20} aria-hidden="true"/></button>}
    </header>

    <main className="clb-main" id="conteudo">
      {loading&&<div className="clb-card clb-state" role="status"><span className="clb-spinner" aria-hidden="true"/>Carregando o clube…</div>}
      {error&&<div className="clb-alert is-danger" role="alert"><TriangleAlert size={20} aria-hidden="true"/><span>{error}</span></div>}
      {!loading&&club&&!me&&<Guest slug={slug} club={club} token={token} ready={ready}
        onEntered={account=>{setToken("");setMe(account);openSection("home");}}/>}
      {!loading&&club&&me&&<Member slug={slug} club={club} me={me} section={section} onOpen={openSection}
        onLogout={()=>void logout()} onChange={next=>setMe(next)}/>}
      {!loading&&!club&&!error&&<div className="clb-card clb-state" role="alert">Clube não encontrado. Confira o endereço com a loja.</div>}
      {support&&<p className="clb-support">Dúvidas sobre o clube? <a href={"mailto:"+support}>Fale com a loja</a></p>}
      <p className="clb-footer"><LockKeyhole size={13} aria-hidden="true"/> Clube com tecnologia Vidalys Fideliza</p>
    </main>

    {me&&<nav className="clb-tabs" aria-label="Seções do clube">
      {([["home","Início",House],["rewards","Trocar",Gift],["history","Extrato",ListOrdered],["rules","Regras",CircleHelp],["profile","Perfil",UserRound]] as const)
        .map(([key,label,Icon])=><button key={key} type="button" className={"clb-tab"+(section===key?" is-on":"")}
          aria-current={section===key?"page":undefined} onClick={()=>openSection(key)}>
          <Icon size={22} aria-hidden="true"/>{label}</button>)}
    </nav>}
  </div>;
}

/* ---------- Cliente que ainda não entrou ---------- */

function Guest({slug,club,token,ready,onEntered}:{slug:string;club:MemberClubPublic;token:string;ready:boolean;
  onEntered:(me:MemberClubPrivate)=>void}){
  const initialMode:Mode = window.location.hash.includes("entrar") || !club.signup_available ? "login" : "join";
  const [mode,setMode] = useState<Mode>(initialMode);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [joined,setJoined] = useState(false);
  const [sent,setSent] = useState(false);
  const [name,setName] = useState("");
  const [email,setEmail] = useState("");
  const [phone,setPhone] = useState("");
  const [accepted,setAccepted] = useState(false);
  const [marketing,setMarketing] = useState(false);
  const [loginEmail,setLoginEmail] = useState("");
  const [code,setCode] = useState("");
  const [remember,setRemember] = useState(true);
  const formRef = useRef<HTMLDivElement>(null);
  const earning = club.earning;
  const gift = giftOf(club);
  const rewards = gift?[]:club.published_rewards||[];
  const cheapest = rewards.filter(r=>r.points_cost>0).sort((a,b)=>a.points_cost-b.points_cost)[0];

  useEffect(()=>{
    if(window.location.hash.includes("participar")||window.location.hash.includes("entrar"))
      formRef.current?.scrollIntoView({block:"start"});
  },[]);

  const join = async (event:FormEvent) => {
    event.preventDefault();
    if(!club.terms||!accepted||busy||!ready) return;
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.joinStore(slug,{name:name.trim(),email:email.trim(),terms_version:club.terms.version,
        accepted_terms:true,marketing_opt_in:marketing,...(phone.trim()?{phone:phone.trim()}:{})});
      setJoined(true);
    }catch(cause){setError(cause instanceof ApiError?cause.message:"Não foi possível registrar sua participação. Tente novamente.");}
    finally{setBusy(false);}
  };
  const requestAccess = async (event:FormEvent) => {
    event.preventDefault();
    if(busy||!ready) return;
    setBusy(true);setError("");
    try{await publicEnrollmentApi.clubRequestAccess(slug,loginEmail.trim());setSent(true);}
    catch(cause){setError(cause instanceof ApiError?cause.message:"Não foi possível enviar o link. Tente novamente.");}
    finally{setBusy(false);}
  };
  const confirm = async () => {
    if(!ready||busy||!token) return;
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.clubConfirmAccess(slug,token,remember);
      onEntered(await publicEnrollmentApi.clubMe(slug));
    }catch(cause){setError(cause instanceof ApiError?cause.message:"Este link não pôde ser confirmado. Peça um novo.");}
    finally{setBusy(false);}
  };

  const enterWithCode = async (event:FormEvent) => {
    event.preventDefault();
    if(busy||!ready) return;
    setBusy(true);setError("");
    try{
      await publicEnrollmentApi.clubEnterWithCode(slug,loginEmail.trim(),code,remember);
      onEntered(await publicEnrollmentApi.clubMe(slug));
    }catch(cause){setError(cause instanceof ApiError?cause.message:"Código incorreto ou expirado. Peça um novo.");}
    finally{setBusy(false);}
  };
  const rememberBox = <label className="clb-check"><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/>
    <span>Manter conectado neste aparelho <small>(até 6 meses; desmarque em aparelho compartilhado)</small></span></label>;

  return <div className="clb-stack">
    <section className="clb-hero" aria-labelledby="clb-hero-title">
      <span className="clb-eyebrow">{club.branding.program_name||("Clube "+club.store_name)}</span>
      <h1 id="clb-hero-title">{gift?`Ganhe ${percent(gift.percent_bps/100)} de volta em crédito para a próxima compra.`:earningHeadline(earning)}</h1>
      <p>Na loja ou no site, é só se identificar. Sem cartão, sem app e sem anuidade.</p>
      {!club.points_enabled&&<span className="clb-hero-note"><Clock3 size={15} aria-hidden="true"/>
        A loja está preparando o clube: os pontos começam a contar quando ela ativar.</span>}
    </section>

    <div ref={formRef} className="clb-anchor"/>
    {token?<section className="clb-card clb-center" aria-labelledby="clb-confirm-title">
      <span className="clb-badge"><LockKeyhole size={26} aria-hidden="true"/></span>
      <h2 id="clb-confirm-title">Confirme seu acesso</h2>
      <p>Este link é pessoal, vale uma vez e expira em 15 minutos.</p>
      {rememberBox}
      {error&&<p className="clb-error" role="alert">{error}</p>}
      <button type="button" className="clb-btn is-primary is-wide" disabled={!ready||busy} onClick={()=>void confirm()}>
        {busy?"Confirmando…":"Confirmar e entrar"} <ArrowRight size={18} aria-hidden="true"/></button>
    </section>
    :joined?<Done title="Confira seu e-mail" icon={<Mail size={30} aria-hidden="true"/>}
      text={"Enviamos um link para "+(email.trim()||"o seu e-mail")+". Toque nele para confirmar sua participação. Confira também o spam."}
      action={<button type="button" className="clb-btn is-wide" onClick={()=>{setJoined(false);setMode("login");}}>Já confirmei, quero entrar</button>}/>
    :sent?<form className="clb-card clb-form" aria-labelledby="clb-code-title" onSubmit={e=>void enterWithCode(e)}>
      <span className="clb-badge"><KeyRound size={26} aria-hidden="true"/></span>
      <h2 id="clb-code-title">Digite o código do e-mail</h2>
      <p className="clb-lead">Se <strong>{loginEmail.trim()}</strong> participa do clube, enviamos um código de 6 dígitos e um link. Valem por 15 minutos.</p>
      <label className="clb-field">Código
        <input className="clb-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]*" maxLength={7} required
          value={code} onChange={e=>setCode(e.target.value.replace(/[^0-9]/g,"").slice(0,6))} placeholder="000000"/></label>
      {rememberBox}
      {error&&<p className="clb-error" role="alert">{error}</p>}
      <button type="submit" className="clb-btn is-primary is-wide" disabled={busy||!ready||code.length!==6}>
        {busy?"Entrando…":"Entrar"} <ArrowRight size={18} aria-hidden="true"/></button>
      <button type="button" className="clb-btn is-ghost" onClick={()=>{setSent(false);setCode("");setError("");}}>Usar outro e-mail ou pedir novo código</button>
    </form>
    :mode==="join"&&club.signup_available&&club.terms?<>
      <form className="clb-card clb-form" aria-labelledby="clb-join-title" onSubmit={e=>void join(e)}>
        <h2 id="clb-join-title">Quero participar</h2>
        <label className="clb-field">Seu nome
          <input autoComplete="name" required minLength={3} maxLength={140} value={name}
            onChange={e=>setName(e.target.value)} placeholder="Como podemos te chamar"/></label>
        <label className="clb-field">E-mail
          <input type="email" autoComplete="email" required maxLength={254} value={email}
            onChange={e=>setEmail(e.target.value)} placeholder="voce@email.com"/></label>
        <label className="clb-field">Celular (opcional)
          <input type="tel" inputMode="tel" autoComplete="tel" maxLength={20} value={phone}
            onChange={e=>setPhone(formatPhone(e.target.value))} placeholder="(31) 99999-9999"/>
          <small>Na loja física, basta dizer o número no caixa.</small></label>
        <label className="clb-check"><input type="checkbox" required checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>
          <span>Li e aceito o regulamento e o aviso de privacidade do clube.</span></label>
        <details className="clb-details"><summary>Ler regulamento · versão {club.terms.version}</summary><p>{club.terms.body}</p></details>
        {club.terms.privacy_notice&&<details className="clb-details"><summary>Ler aviso de privacidade</summary><p>{club.terms.privacy_notice}</p></details>}
        <label className="clb-check"><input type="checkbox" checked={marketing} onChange={e=>setMarketing(e.target.checked)}/>
          <span>Quero receber ofertas da loja por e-mail (opcional).</span></label>
        {error&&<p className="clb-error" role="alert">{error}</p>}
        <button type="submit" className="clb-btn is-primary is-wide" disabled={!accepted||busy||!ready}>
          {busy?"Enviando…":"Entrar no clube"} <ArrowRight size={18} aria-hidden="true"/></button>
        <span className="clb-hint">Enviamos um link de confirmação. Sem senha para lembrar.</span>
      </form>
      <section className="clb-card clb-switch" aria-label="Já participa">
        <div><strong>Já participa?</strong><span>Entre com o código que chega no seu e-mail.</span></div>
        <button type="button" className="clb-btn" onClick={()=>{setMode("login");setError("");}}>Entrar</button>
      </section>
    </>
    :<>
      <form className="clb-card clb-form" aria-labelledby="clb-login-title" onSubmit={e=>void requestAccess(e)}>
        <h2 id="clb-login-title">Entrar no Meu Clube</h2>
        <p className="clb-lead">Informe o e-mail que você usou para participar. Enviamos um código e um link, sem senha.</p>
        <label className="clb-field">Seu e-mail
          <input id="clb-login-email" type="email" autoComplete="email" required maxLength={254} value={loginEmail}
            onChange={e=>setLoginEmail(e.target.value)} placeholder="voce@email.com"/></label>
        {error&&<p className="clb-error" role="alert">{error}</p>}
        <button type="submit" className="clb-btn is-primary is-wide" disabled={busy||!ready}>
          {busy?"Enviando…":"Receber código de acesso"} <ArrowRight size={18} aria-hidden="true"/></button>
      </form>
      {club.signup_available&&club.terms?<section className="clb-card clb-switch" aria-label="Ainda não participa">
        <div><strong>Ainda não participa?</strong><span>É grátis e leva menos de um minuto.</span></div>
        <button type="button" className="clb-btn" onClick={()=>{setMode("join");setError("");}}>Participar</button>
      </section>:<p className="clb-hint">As inscrições pelo site ainda não foram abertas pela loja. Peça no caixa.</p>}
    </>}

    <section className="clb-card" aria-labelledby="clb-how-title">
      <h2 id="clb-how-title">Como funciona</h2>
      {gift?<ol className="clb-steps">
        <li><span>1</span><p><strong>Compre na loja ou no site</strong> e diga seu celular no caixa.</p></li>
        <li><span>2</span><p>Você recebe <strong>{percent(gift.percent_bps/100)} da compra em crédito</strong>, até {money(gift.cap_cents)}{gift.hold_days?`, liberado em ${gift.hold_days} dias`:""}.</p></li>
        <li><span>3</span><p><strong>Use em até {gift.validity_days} dias</strong> numa compra a partir de {money(gift.min_order_cents)}. O desconto sai na hora.</p></li>
      </ol>:<ol className="clb-steps">
        <li><span>1</span><p>{earning?<><strong>{earningSentence(earning)}</strong></>:<><strong>Compre na loja ou no site.</strong> Cada compra paga soma pontos.</>}</p></li>
        <li><span>2</span><p>{cheapest?<>Com <strong>{pts(cheapest.points_cost)} pontos</strong> você troca por {money(cheapest.discount_cents)} de desconto.</>
          :<>Troque os pontos por descontos <strong>assim que a loja publicar as recompensas.</strong></>}</p></li>
        <li><span>3</span><p>{earning&&earning.hold_days>0?<>Os pontos entram depois de <strong>{earning.hold_days} dias</strong>, o prazo de troca da compra.</>
          :<>Os pontos entram depois que a loja confere a compra.</>}{earning&&earning.validity_days>0?<> Valem por <strong>{earning.validity_days} dias</strong>.</>:null}</p></li>
      </ol>}
    </section>

    {rewards.length>0&&<section className="clb-card" aria-labelledby="clb-catalog-title">
      <h2 id="clb-catalog-title">O que dá para trocar</h2>
      <ul className="clb-list">{rewards.slice(0,6).map(r=><li key={r.id} className="clb-reward">
        <span className="clb-reward-ico">{shortMoney(r.discount_cents)}</span>
        <div><strong>{r.title}</strong><span>{pts(r.points_cost)} pontos{r.min_order_cents>0?" · compra mínima "+money(r.min_order_cents):""}</span></div>
      </li>)}</ul>
    </section>}
  </div>;
}

function Done({title,text,icon,action}:{title:string;text:string;icon:ReactNode;action:ReactNode}){
  return <section className="clb-card clb-center" role="status">
    <span className="clb-badge is-ok">{icon}</span>
    <h2>{title}</h2><p>{text}</p>{action}
  </section>;
}

/* ---------- Cliente que entrou ---------- */

function Member({slug,club,me,section,onOpen,onLogout,onChange}:{slug:string;club:MemberClubPublic;me:MemberClubPrivate;
  section:ClubSection;onOpen:(s:ClubSection)=>void;onLogout:()=>void;onChange:(me:MemberClubPrivate)=>void}){
  const [showCounter,setShowCounter] = useState(false);
  const atCounter = me.redemption_place==="counter";
  const verified = (me.points_status==="verified"||me.points_status==="counter") && typeof me.points_balance==="number";
  const balance = typeof me.points_balance==="number" ? me.points_balance : null;
  const rewards = me.available_rewards||[];
  const ready = rewards.filter(r=>me.redemption_enabled&&r.redemption_enabled&&r.status==="available"&&r.redemption_unit==="points");
  const next = rewards.filter(r=>r.status!=="paused"&&r.status!=="sold_out"&&r.points_cost>0&&(balance===null||r.points_cost>balance))
    .sort((a,b)=>a.points_cost-b.points_cost)[0];
  const earning = club.earning;
  const gift = giftOf(club);

  return <>
    {section==="home"&&<div className="clb-stack">
      {gift?<section className="clb-wallet" aria-label="Seu crédito">
        <span className="clb-eyebrow">SEU CRÉDITO</span>
        <strong className="clb-big">{balance!==null?money(balance):"—"}</strong>
        <span className="clb-wallet-line">{balance!==null?<>para usar numa compra a partir de <b>{money(gift.min_order_cents)}</b></>
          :me.status==="active"?"Seu crédito aparece aqui depois da primeira compra conferida.":"Seu cadastro está sendo conferido pela loja."}</span>
        {typeof me.points_pending==="number"&&me.points_pending>0&&<span className="clb-wallet-sub">+{money(me.points_pending)} a liberar, aguardando o prazo da compra</span>}
        {atCounter&&<span className="clb-wallet-sub">Use no caixa da loja: diga seu celular e peça para aplicar o crédito.</span>}
        <button type="button" className="clb-btn is-light" onClick={()=>setShowCounter(true)}><ScanLine size={18} aria-hidden="true"/> Mostrar no caixa</button>
      </section>
      :<section className="clb-wallet" aria-label="Seu saldo">
        <span className="clb-eyebrow">SEU SALDO</span>
        <strong className="clb-big">{balance!==null?pts(balance):"—"}</strong>
        {balance!==null?<span className="clb-wallet-line">pontos = <b>{money(balance)}</b> em descontos</span>
          :<span className="clb-wallet-line">{me.status==="active"?"A loja ainda não ativou a pontuação. Seu saldo aparece aqui quando começar."
            :"Seu cadastro está sendo conferido pela loja."}</span>}
        {typeof me.points_pending==="number"&&me.points_pending>0&&<span className="clb-wallet-sub">+{pts(me.points_pending)} pontos pendentes, aguardando o prazo da compra</span>}
        {me.points_status==="ledger_only"&&<span className="clb-wallet-sub">Saldo em conferência: ainda não pode ser trocado.</span>}
        {atCounter&&<span className="clb-wallet-sub">Troque seus pontos no caixa da loja: o vendedor aplica o vale na compra.</span>}
        <button type="button" className="clb-btn is-light" onClick={()=>setShowCounter(true)}><ScanLine size={18} aria-hidden="true"/> Mostrar no caixa</button>
      </section>}

      {(me.offers||[]).length>0&&<section className="clb-offers" aria-labelledby="clb-offers-title">
        <h2 id="clb-offers-title" className="clb-section-label">Para você</h2>
        {(me.offers||[]).map(o=><OfferCard key={o.id} offer={o} live={club.points_enabled}/>)}
      </section>}

      {typeof me.points_expiring==="number"&&me.points_expiring>0&&<div className="clb-alert is-warn" role="status">
        <Clock3 size={20} aria-hidden="true"/><div><strong>{gift?money(me.points_expiring)+" de crédito vence em breve":pts(me.points_expiring)+" pontos vencem em breve"}</strong>
          <span>{gift?"Use na próxima compra antes de perder.":"Troque antes de perder. Veja as opções em Trocar."}</span></div></div>}
      {me.status!=="active"&&<div className="clb-alert is-info" role="status"><Store size={20} aria-hidden="true"/>
        <div><strong>{me.status==="paused"?"Participação pausada":"Cadastro aguardando a loja"}</strong>
          <span>{me.status==="paused"?"Fale com a loja para retomar.":"Assim que a loja confirmar seu cadastro, suas compras passam a contar."}</span></div></div>}

      {!gift&&next&&<section className="clb-card" aria-labelledby="clb-next-title">
        <div className="clb-card-head"><h2 id="clb-next-title">Próxima troca</h2>
          {balance!==null&&<span>faltam {pts(next.points_cost-balance)} pontos</span>}</div>
        <div className="clb-reward is-flat"><span className="clb-reward-ico is-gold">{shortMoney(next.discount_cents)}</span>
          <div><strong>{money(next.discount_cents)} de desconto</strong>
            <span>{pts(next.points_cost)} pontos{spendFor(earning,next.points_cost)?" · cerca de "+money(spendFor(earning,next.points_cost) as number)+" em compras":""}</span></div></div>
        {balance!==null&&<div className="clb-bar" role="progressbar" aria-label="Progresso até a próxima troca"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(100,Math.round(balance/next.points_cost*100))}>
          <span style={{width:Math.min(100,Math.round(balance/next.points_cost*100))+"%"}}/></div>}
      </section>}

      {!gift&&ready.length>0&&<section className="clb-card" aria-labelledby="clb-now-title">
        <h2 id="clb-now-title">Você já pode trocar</h2>
        <ul className="clb-list">{ready.slice(0,3).map(r=><li key={r.id} className="clb-reward">
          <span className="clb-reward-ico">{shortMoney(r.discount_cents)}</span>
          <div><strong>{money(r.discount_cents)} de desconto</strong><span>{pts(r.points_cost)} pontos</span></div>
          <button type="button" className="clb-btn is-primary is-small" onClick={()=>onOpen("rewards")}>Trocar</button></li>)}</ul>
      </section>}

      {!gift&&rewards.length===0&&<section className="clb-card clb-empty"><Gift size={24} aria-hidden="true"/>
        <div><strong>Recompensas a caminho</strong><span>Quando a loja publicar as trocas, elas aparecem aqui.</span></div></section>}

      <ProfileNudge me={me} onOpen={()=>onOpen("profile")}/>

      {(me.vip_level||me.vip_next_level)&&<MemberVipCard me={me}/>}
      {(me.missions||[]).length>0&&<MemberMissions me={me}/>}

      <button type="button" className="clb-card clb-link-card" onClick={()=>onOpen("rules")}>
        <span className="clb-reward-ico is-soft"><BookOpen size={22} aria-hidden="true"/></span>
        <div><strong>Como funciona o clube</strong><span>{gift?giftSentence(gift):earning?earningSentence(earning):"Veja as regras e o regulamento."}</span></div>
        <ArrowRight size={18} aria-hidden="true"/></button>
    </div>}

    {section==="rewards"&&(gift?<div className="clb-stack">
      <div className="clb-page-head"><h1>Usar crédito</h1><span>{balance!==null?"Você tem "+money(balance)+" de crédito.":"Seu crédito aparece depois da primeira compra conferida."}</span></div>
      <section className="clb-card"><ol className="clb-steps">
        <li><span>1</span><p>Na hora de pagar, <strong>diga seu celular</strong> ao vendedor.</p></li>
        <li><span>2</span><p>Peça para <strong>usar o crédito</strong>. Ele vale em compras a partir de {money(gift.min_order_cents)}.</p></li>
        <li><span>3</span><p>O desconto sai na mesma compra, e a compra nova já gera crédito para a próxima.</p></li>
      </ol></section></div>
      :<Redeem slug={slug} me={me} balance={balance} verified={verified}/>)}
    {section==="history"&&<History me={me}/>}
    {section==="rules"&&<Rules slug={slug} club={club} me={me}/>}
    {section==="profile"&&<Profile slug={slug} club={club} me={me} onLogout={onLogout} onChange={onChange}/>}

    {showCounter&&<CounterSheet me={me} onClose={()=>setShowCounter(false)}/>}
  </>;
}

function CounterSheet({me,onClose}:{me:MemberClubPrivate;onClose:()=>void}){
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(()=>{
    closeRef.current?.focus();
    const esc = (e:KeyboardEvent) => {if(e.key==="Escape") onClose();};
    document.addEventListener("keydown",esc);
    return ()=>document.removeEventListener("keydown",esc);
  },[onClose]);
  return <div className="clb-sheet" onMouseDown={e=>{if(e.target===e.currentTarget) onClose();}}>
    <div className="clb-sheet-body" role="dialog" aria-modal="true" aria-labelledby="clb-counter-title">
      <span className="clb-sheet-grip" aria-hidden="true"/>
      <h2 id="clb-counter-title">Mostre ao vendedor</h2>
      <div className="clb-counter-id">
        <span className="clb-store-tile is-big" aria-hidden="true">{initials(me.display_name)}</span>
        <strong>{me.display_name}</strong>
        <span>{me.phone_last4?"Celular final "+me.phone_last4:"Diga seu nome e e-mail no caixa"}</span>
      </div>
      <p>{me.phone_last4?"Diga seu celular no caixa. O vendedor encontra seu cadastro e registra a compra no clube."
        :"O vendedor procura seu cadastro pelo nome. Para ser mais rápido, informe seu celular na próxima compra."}</p>
      <button ref={closeRef} type="button" className="clb-btn is-wide" onClick={onClose}><X size={18} aria-hidden="true"/> Fechar</button>
    </div>
  </div>;
}

function rewardState(r:MemberClubReward, me:MemberClubPrivate, balance:number|null){
  if(r.status==="paused") return "Pausada";
  if(r.status==="sold_out") return "Esgotada";
  if(me.redemption_enabled&&r.redemption_enabled&&r.status==="available"&&r.redemption_unit==="points") return null;
  if(balance!==null&&balance<r.points_cost) return "faltam "+pts(r.points_cost-balance);
  if(me.redemption_place==="counter"&&balance!==null) return "Troque no caixa";
  return "Em breve";
}

type Voucher = {code:string;discount_cents:number;expires_at:string;external_coupon_created:boolean};

function Redeem({slug,me,balance,verified}:{slug:string;me:MemberClubPrivate;balance:number|null;verified:boolean}){
  const [busy,setBusy] = useState("");
  const [issued,setIssued] = useState<Voucher|null>(null);
  const [error,setError] = useState("");
  const rewards = me.available_rewards||[];
  const redeem = async (r:MemberClubReward) => {
    if(busy) return;
    setBusy(r.id);setError("");setIssued(null);
    try{setIssued(await publicEnrollmentApi.clubIssueVoucher(slug,r.id));}
    catch(cause){setError(cause instanceof ApiError?cause.message:"Não foi possível trocar agora. Confira o saldo e tente de novo.");}
    finally{setBusy("");}
  };
  return <div className="clb-stack">
    <div className="clb-page-head"><h1>Trocar pontos</h1>
      <span>{balance!==null?"Você tem "+pts(balance)+" pontos ("+money(balance)+").":"Seu saldo aparece quando a loja ativar a pontuação."}</span></div>
    {me.redemption_place==="counter"&&<div className="clb-alert is-info" role="status"><Store size={20} aria-hidden="true"/>
      <div><strong>Trocas no caixa da loja</strong><span>Na hora de pagar, diga seu celular ao vendedor e peça para usar o vale. O desconto sai na mesma compra.</span></div></div>}
    {!me.redemption_enabled&&me.redemption_place!=="counter"&&<div className="clb-alert is-info" role="status"><LockKeyhole size={20} aria-hidden="true"/>
      <div><strong>Trocas ainda não abertas</strong><span>{verified?"A loja ainda não liberou o resgate.":"Você já pode conhecer as recompensas. A troca abre quando a loja ativar o clube."}</span></div></div>}
    {issued&&<section className="clb-card clb-center is-ok" role="status">
      <span className="clb-badge is-ok"><CheckCircle2 size={28} aria-hidden="true"/></span>
      <h2>Cupom pronto: <code>{issued.code}</code></h2>
      <p>{issued.external_coupon_created?"Use no site da loja ou mostre no caixa. ":"Mostre este código no caixa. "}
        Vale {money(issued.discount_cents)} até {new Date(issued.expires_at).toLocaleDateString("pt-BR")}, uma vez.</p>
    </section>}
    {error&&<div className="clb-alert is-danger" role="alert"><TriangleAlert size={20} aria-hidden="true"/><span>{error}</span></div>}
    {rewards.length===0?<section className="clb-card clb-empty"><Gift size={24} aria-hidden="true"/>
      <div><strong>Nenhuma recompensa publicada</strong><span>Quando a loja publicar as trocas, elas aparecem aqui.</span></div></section>
    :<ul className="clb-list is-cards">{rewards.map(r=>{
      const state = rewardState(r,me,balance);
      return <li key={r.id} className={"clb-reward is-card"+(state?" is-locked":"")}>
        <span className="clb-reward-ico">{shortMoney(r.discount_cents)}</span>
        <div><strong>{r.title}</strong><span>{pts(r.points_cost)} pontos{r.min_order_cents>0?" · compra mínima "+money(r.min_order_cents):""}</span></div>
        {state?<span className="clb-chip">{state}</span>
          :<button type="button" className="clb-btn is-primary is-small" disabled={Boolean(busy)} onClick={()=>void redeem(r)}>
            {busy===r.id?"Trocando…":"Trocar"}</button>}
      </li>;})}</ul>}
  </div>;
}

function History({me}:{me:MemberClubPrivate}){
  return <div className="clb-stack">
    <div className="clb-page-head"><h1>Extrato</h1><span>Cada ponto, de onde veio e quando entrou.</span></div>
    {me.transactions.length?<section className="clb-card is-flush"><ul className="clb-rows">
      {me.transactions.map(t=><li key={t.id}>
        <span className={"clb-row-ico "+(t.points_delta<0?"is-out":"is-in")} aria-hidden="true">{t.points_delta<0?<TicketPercent size={18}/>:<Sparkles size={18}/>}</span>
        <div><strong>{t.description}</strong><span>{new Date(t.created_at).toLocaleDateString("pt-BR",{day:"2-digit",month:"short",year:"numeric"})}</span></div>
        <b className={t.points_delta<0?"is-out":"is-in"}>{t.points_delta>0?"+":t.points_delta<0?"−":""}{pts(Math.abs(t.points_delta))}</b>
      </li>)}</ul></section>
    :<section className="clb-card clb-empty"><ListOrdered size={24} aria-hidden="true"/>
      <div><strong>Nenhuma movimentação ainda</strong><span>Suas compras e trocas aparecem aqui assim que a loja registrar.</span></div></section>}
  </div>;
}

function Rules({slug,club,me}:{slug:string;club:MemberClubPublic;me:MemberClubPrivate}){
  const e = club.earning;
  const gift = giftOf(club);
  const rewards = club.published_rewards||me.available_rewards||[];
  const cheapest = rewards.filter(r=>r.points_cost>0).sort((a,b)=>a.points_cost-b.points_cost)[0];
  const items:ReactNode[] = [];
  if(gift){
    items.push(<><strong>Ganhe {percent(gift.percent_bps/100)} de volta em crédito.</strong> Até {money(gift.cap_cents)} por compra.</>);
    items.push(gift.hold_days>0?<><strong>O crédito libera em {gift.hold_days} dias.</strong> É o prazo de troca. Compra cancelada não gera crédito.</>
      :<><strong>O crédito entra após a conferência.</strong> Compra cancelada não gera crédito.</>);
    items.push(<><strong>Use em até {gift.validity_days} dias</strong> numa compra a partir de {money(gift.min_order_cents)}, no caixa da loja.</>);
  }else if(e){
    items.push(<><strong>Ganhe {percent(e.points/e.per_cents*100)} de volta.</strong> {earningSentence(e)}</>);
    items.push(e.hold_days>0?<><strong>Pontos liberam em {e.hold_days} dias.</strong> É o prazo de troca. Compra cancelada não gera pontos.</>
      :<><strong>Pontos entram após a conferência.</strong> Compra cancelada não gera pontos.</>);
    if(e.validity_days>0) items.push(<><strong>Valem {e.validity_days} dias.</strong> Depois disso, os pontos não usados expiram.</>);
  }else items.push(<><strong>Compre e junte pontos.</strong> A loja ainda está definindo quantos pontos cada compra gera.</>);
  if(!gift) items.push(cheapest?<><strong>Troque a partir de {pts(cheapest.points_cost)} pontos.</strong> No site ou no caixa da loja.</>
    :<><strong>Trocas em breve.</strong> As recompensas aparecem em Trocar quando a loja publicar.</>);
  return <div className="clb-stack">
    <div className="clb-page-head"><h1>Como funciona</h1>
      <span className={"clb-chip "+(club.points_enabled?"is-ok":"is-gold")}>{club.points_enabled?"Clube ativo":"Clube em preparação"}</span></div>
    <section className="clb-card"><ol className="clb-steps">{items.map((item,i)=><li key={i}><span>{i+1}</span><p>{item}</p></li>)}</ol></section>
    <section className="clb-card" aria-labelledby="clb-terms-title">
      <h2 id="clb-terms-title">Regulamento e privacidade</h2>
      <p className="clb-lead">Você aceitou {me.terms.title}, versão {me.terms.version}.</p>
      <details className="clb-details"><summary>Ler o regulamento completo</summary><p>{me.terms.body}</p></details>
      {me.terms.privacy_notice&&<details className="clb-details"><summary>Ler o aviso de privacidade</summary><p>{me.terms.privacy_notice}</p></details>}
      <a className="clb-text-link" href={"/retirar/"+encodeURIComponent(slug)}><ShieldCheck size={16} aria-hidden="true"/> Quero sair do clube</a>
    </section>
  </div>;
}

/* ---------- Ofertas, perfil e app ---------- */

const MONTHS = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];
const daysLeft = (iso:string|null) => {
  if(!iso) return null;
  const end = new Date(iso+"T23:59:59");
  return Math.max(0, Math.ceil((end.getTime()-Date.now())/86400000));
};

function OfferCard({offer,live}:{offer:MemberOffer;live:boolean}){
  const left = daysLeft(offer.ends_on);
  const Icon = offer.goal==="birthday" ? Cake : offer.goal==="multiplier" ? Sparkles : Gift;
  return <article className="clb-offer">
    <span className="clb-offer-ico" aria-hidden="true"><Icon size={22}/></span>
    <div>
      <strong>{offer.title}</strong>
      <span>{offer.message}</span>
      <em>{left===null?"Por tempo limitado":left===0?"Termina hoje":left===1?"Termina amanhã":"Faltam "+left+" dias"}
        {!live&&" · os pontos entram quando a loja ativar o clube"}</em>
    </div>
  </article>;
}

function completeness(me:MemberClubPrivate){
  const items = [Boolean(me.display_name), Boolean(me.phone_last4), Boolean(me.birth_day&&me.birth_month)];
  return Math.round(items.filter(Boolean).length/items.length*100);
}

function ProfileNudge({me,onOpen}:{me:MemberClubPrivate;onOpen:()=>void}){
  const pct = completeness(me);
  if(pct>=100) return null;
  const missing = [!me.phone_last4&&"celular", !(me.birth_day&&me.birth_month)&&"aniversário"].filter(Boolean).join(" e ");
  return <button type="button" className="clb-card clb-link-card clb-nudge" onClick={onOpen}>
    <span className="clb-ring" style={{"--pct":pct} as CSSProperties} aria-hidden="true"><span>{pct}%</span></span>
    <div><strong>Complete seu perfil</strong><span>Adicione {missing}: identificação mais rápida no caixa e presente no seu mês.</span></div>
    <ArrowRight size={18} aria-hidden="true"/></button>;
}

function Profile({slug,club,me,onLogout,onChange}:{slug:string;club:MemberClubPublic;me:MemberClubPrivate;
  onLogout:()=>void;onChange:(me:MemberClubPrivate)=>void}){
  const [name,setName] = useState(me.display_name);
  const [phone,setPhone] = useState("");
  const [day,setDay] = useState(me.birth_day?String(me.birth_day):"");
  const [month,setMonth] = useState(me.birth_month?String(me.birth_month):"");
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState("");
  const [error,setError] = useState("");
  const [install,setInstall] = useState<InstallState>(()=>installState());
  useEffect(()=>onInstallChange(()=>setInstall(installState())),[]);
  const pct = completeness(me);

  const apply = async (data:Parameters<typeof publicEnrollmentApi.clubUpdateProfile>[1], done:string) => {
    setBusy(true);setError("");setNotice("");
    try{
      const {profile} = await publicEnrollmentApi.clubUpdateProfile(slug,data);
      onChange({...me,...profile});
      setPhone("");setNotice(done);
    }catch(cause){setError(cause instanceof ApiError?cause.message:"Não foi possível salvar. Tente novamente.");}
    finally{setBusy(false);}
  };
  const save = (event:FormEvent) => {
    event.preventDefault();
    if(busy) return;
    const data:Parameters<typeof publicEnrollmentApi.clubUpdateProfile>[1] = {};
    if(name.trim()!==me.display_name) data.name = name.trim();
    if(phone.trim()) data.phone = phone.trim();
    const d = day?Number(day):null, m = month?Number(month):null;
    if((d===null)!==(m===null)){setError("Escolha o dia e o mês do aniversário.");return;}
    if(d!==(me.birth_day??null)||m!==(me.birth_month??null)){data.birth_day=d;data.birth_month=m;}
    if(!Object.keys(data).length){setNotice("Nada mudou.");return;}
    void apply(data,"Perfil atualizado.");
  };
  const installNow = async () => {
    const ok = await promptInstall();
    setInstall(installState());
    if(ok) setNotice("Pronto! O clube está na tela inicial do seu celular.");
  };
  const until = me.session_expires_at ? new Date(me.session_expires_at) : null;
  const long = until ? until.getTime()-Date.now() > 3*86400000 : false;

  return <div className="clb-stack">
    <section className="clb-card clb-profile-head" aria-label="Seu perfil">
      <span className="clb-store-tile is-big" aria-hidden="true">{initials(me.display_name)}</span>
      <div><h1>{me.display_name}</h1><span>{me.email}</span></div>
      <div className="clb-profile-meter">
        <div className="clb-bar" role="progressbar" aria-label="Perfil completo" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <span style={{width:pct+"%"}}/></div>
        <small>{pct===100?"Perfil completo":"Perfil "+pct+"% completo"}</small>
      </div>
    </section>

    {notice&&<div className="clb-alert is-ok" role="status"><CheckCircle2 size={20} aria-hidden="true"/><span>{notice}</span></div>}
    {error&&<div className="clb-alert is-danger" role="alert"><TriangleAlert size={20} aria-hidden="true"/><span>{error}</span></div>}

    <form className="clb-card clb-form" aria-labelledby="clb-data-title" onSubmit={save}>
      <h2 id="clb-data-title">Seus dados</h2>
      <label className="clb-field">Nome
        <input autoComplete="name" minLength={3} maxLength={140} value={name} onChange={e=>setName(e.target.value)}/></label>
      <label className="clb-field">Celular
        <input type="tel" inputMode="tel" autoComplete="tel" maxLength={20} value={phone} onChange={e=>setPhone(formatPhone(e.target.value))}
          placeholder={me.phone_last4?"Cadastrado: final "+me.phone_last4+" · digite para trocar":"(31) 99999-9999"}/>
        <small>{me.phone_last4?"Guardamos o número protegido; aparecem só os 4 últimos dígitos.":"Com o celular, o vendedor encontra você no caixa em segundos."}</small></label>
      <fieldset className="clb-birth">
        <legend>Aniversário <small>(sem o ano)</small></legend>
        <label className="clb-field"><span className="clb-sr">Dia</span>
          <select value={day} onChange={e=>setDay(e.target.value)} aria-label="Dia do aniversário">
            <option value="">Dia</option>{Array.from({length:31},(_,i)=><option key={i+1} value={i+1}>{i+1}</option>)}</select></label>
        <label className="clb-field"><span className="clb-sr">Mês</span>
          <select value={month} onChange={e=>setMonth(e.target.value)} aria-label="Mês do aniversário">
            <option value="">Mês</option>{MONTHS.map((label,i)=><option key={label} value={i+1}>{label}</option>)}</select></label>
      </fieldset>
      <button type="submit" className="clb-btn is-primary is-wide" disabled={busy}>{busy?"Salvando…":"Salvar perfil"}</button>
      {me.phone_last4&&<button type="button" className="clb-btn is-ghost" disabled={busy} onClick={()=>void apply({phone:""},"Celular removido.")}>Remover celular</button>}
    </form>

    <section className="clb-card" aria-labelledby="clb-notify-title">
      <h2 id="clb-notify-title">Avisos</h2>
      <div className="clb-toggle-row">
        <div><strong>Ofertas e pontos por e-mail</strong><span>Campanhas, pontos perto de vencer e novidades da loja.</span></div>
        <button type="button" role="switch" aria-checked={Boolean(me.marketing_opt_in)} aria-label="Receber ofertas por e-mail"
          className={"clb-switch-btn"+(me.marketing_opt_in?" is-on":"")} disabled={busy}
          onClick={()=>void apply({marketing_opt_in:!me.marketing_opt_in},me.marketing_opt_in?"Você não vai mais receber ofertas por e-mail.":"Pronto! Você vai receber as ofertas por e-mail.")}>
          <span/></button>
      </div>
      <p className="clb-hint is-left">Notificações no celular chegam numa próxima versão do app.</p>
    </section>

    <section className="clb-card" aria-labelledby="clb-app-title">
      <div className="clb-app-head"><span className="clb-reward-ico is-soft"><Smartphone size={22} aria-hidden="true"/></span>
        <div><h2 id="clb-app-title">App do clube</h2><span>{club.branding.program_name} na tela inicial, abre direto no seu saldo.</span></div></div>
      {install==="installed"?<p className="clb-app-done"><CheckCircle2 size={18} aria-hidden="true"/> Você está usando o app do clube.</p>
      :install==="ready"?<button type="button" className="clb-btn is-primary is-wide" onClick={()=>void installNow()}><Download size={18} aria-hidden="true"/> Instalar app</button>
      :install==="ios"?<ol className="clb-steps is-compact">
        <li><span>1</span><p>Toque em <strong>Compartilhar</strong> <Share size={15} aria-label="ícone de compartilhar"/> na barra do Safari.</p></li>
        <li><span>2</span><p>Escolha <strong>Adicionar à Tela de Início</strong>.</p></li>
        <li><span>3</span><p>Toque em <strong>Adicionar</strong>. Pronto!</p></li></ol>
      :<p className="clb-lead">Abra este endereço no <strong>Chrome</strong> (Android) ou no <strong>Safari</strong> (iPhone) do celular para instalar.</p>}
    </section>

    <section className="clb-card" aria-labelledby="clb-access-title">
      <h2 id="clb-access-title">Acesso</h2>
      <p className="clb-lead"><CalendarDays size={16} aria-hidden="true"/> {until?(long?"Este aparelho fica conectado até "+until.toLocaleDateString("pt-BR",{day:"2-digit",month:"long"})+".":"Sessão válida até "+until.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})+". Na próxima entrada, marque “Manter conectado”."):"Você entra com um código enviado ao seu e-mail, sem senha."}</p>
      <button type="button" className="clb-btn" onClick={onLogout}><LogOut size={17} aria-hidden="true"/> Sair desta conta</button>
    </section>

    <section className="clb-card" aria-labelledby="clb-privacy-title">
      <h2 id="clb-privacy-title">Privacidade</h2>
      <a className="clb-text-link" href={publicEnrollmentApi.clubExportUrl(slug)} download><Download size={16} aria-hidden="true"/> Baixar meus dados</a>
      <a className="clb-text-link is-danger" href={"/retirar/"+encodeURIComponent(slug)}><ShieldCheck size={16} aria-hidden="true"/> Sair do clube e retirar meu consentimento</a>
    </section>
  </div>;
}
