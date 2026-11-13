import {useEffect,useState,type FormEvent} from "react";
import {ArrowRight,CheckCircle2,Eye,EyeOff,Gift,KeyRound,LockKeyhole,Mail,ShieldCheck} from "lucide-react";
import {ApiError,merchantApi} from "./api";

type View="login"|"signup"|"await-email"|"confirm"|"forgot"|"reset"|"reset-sent"|"reset-complete";
const pathView=():View=>{
  const path=window.location.pathname;
  if(path==="/cadastrar")return "signup";
  if(path==="/confirmar-conta")return "confirm";
  if(path==="/esqueci-senha")return "forgot";
  if(path==="/redefinir-senha")return "reset";
  return "login";
};
const viewPath:Record<View,string>={
  login:"/",signup:"/cadastrar","await-email":"/cadastrar",confirm:"/confirmar-conta",
  forgot:"/esqueci-senha",reset:"/redefinir-senha","reset-sent":"/esqueci-senha",
  "reset-complete":"/redefinir-senha",
};

function Brand(){
  return <div className="merchant-brand">
    <span className="merchant-logo" aria-hidden="true">V</span>
    <span className="merchant-wordmark">vidalys<span>fideliza</span></span>
  </div>;
}

export default function MerchantAccess({
  onLogin, onVerified, onSwitchAccount, onNavigate, activeAccount, busy, authError,
}:{
  onLogin:(email:string,password:string)=>Promise<void>;
  onVerified:()=>Promise<void>;
  onSwitchAccount:()=>Promise<void>;
  onNavigate:(path:string)=>void;
  activeAccount:string|null;
  busy:boolean;
  authError:string;
}){
  const [view,setView]=useState<View>(pathView);
  const [token,setToken]=useState(()=>{
    const params=new URLSearchParams(window.location.hash.replace(/^#/,""));
    return params.get("token")||"";
  });
  const [name,setName]=useState("");
  const [store,setStore]=useState("");
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [confirm,setConfirm]=useState("");
  const [showPassword,setShowPassword]=useState(false);
  const [pending,setPending]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  const clearForm=()=>{
    setName("");setStore("");setEmail("");setPassword("");setConfirm("");
    setShowPassword(false);setToken("");
  };

  useEffect(()=>{
    // Remove a prova do endereco visivel apos capturar a fragment URL.
    if(window.location.hash.startsWith("#token=")){
      window.history.replaceState(null,"",window.location.pathname);
    }
    const sync=()=>{
      const next=pathView();
      setName("");setStore("");setEmail("");setPassword("");setConfirm("");
      setShowPassword(false);setToken("");
      setView(next);setError("");setMessage("");
      if(next==="confirm"||next==="reset"){
        setToken(new URLSearchParams(window.location.hash.replace(/^#/,"")).get("token")||"");
        if(window.location.hash)window.history.replaceState(null,"",window.location.pathname);
      }
    };
    window.addEventListener("popstate",sync);
    return ()=>window.removeEventListener("popstate",sync);
  },[]);

  const go=(next:View)=>{
    setError("");setMessage("");clearForm();
    window.history.pushState(null,"",viewPath[next]);
    setView(next);
    onNavigate(viewPath[next]);
  };

  const switchAccount=async()=>{
    if(pending||busy)return;
    setPending(true);setError("");
    try{
      await onSwitchAccount();
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível sair da conta atual.");
    }finally{setPending(false);}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(pending||busy)return;
    setError("");setMessage("");
    if(view==="login"){
      try{await onLogin(email.trim(),password);}
      finally{setPassword("");}
      return;
    }
    if((view==="signup"||view==="reset")&&password!==confirm){
      setError("As senhas não conferem.");return;
    }
    setPending(true);
    try{
      if(view==="signup"){
        await merchantApi.registerMerchant({
          name:name.trim(),store_name:store.trim(),email:email.trim(),password
        });
        setName("");setStore("");setPassword("");setConfirm("");
        setShowPassword(false);setView("await-email");
      }else if(view==="confirm"){
        if(!token)throw new Error("Link de confirmação inválido. Solicite outro e-mail.");
        await merchantApi.confirmMerchant(token);
        clearForm();
        await onVerified();
      }else if(view==="forgot"){
        await merchantApi.requestMerchantReset(email.trim());
        clearForm();setView("reset-sent");
      }else if(view==="reset"){
        if(!token)throw new Error("Link inválido. Solicite uma nova redefinição de senha.");
        await merchantApi.confirmMerchantReset(token,password);
        clearForm();
        window.history.replaceState(null,"","/redefinir-senha");
        setView("reset-complete");
        setMessage("Senha redefinida. Você já pode entrar com a nova senha.");
      }
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:
        cause instanceof Error?cause.message:"Não foi possível concluir. Tente novamente.");
    }finally{setPending(false);}
  };

  const resend=async()=>{
    if(pending)return;
    setPending(true);setError("");
    try{
      await merchantApi.resendMerchantEmail(email.trim());
      setMessage("Se a solicitação ainda estiver válida, enviaremos um novo e-mail.");
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível reenviar.");
    }finally{setPending(false);}
  };
  const actionBusy=busy||pending;
  const headings:Record<View,[string,string]>={
    login:["Bem-vindo de volta.","Entre para administrar seu programa de fidelidade."],
    signup:["Crie sua conta.","Seu programa começa aqui. Não é necessário ter loja virtual."],
    "await-email":["Verifique seu e-mail.","Se existir um cadastro aguardando confirmação, um link será enviado. Se você já confirmou a conta, pode entrar normalmente."],
    confirm:["Confirme seu e-mail.","Conclua sua conta de lojista e abra seu painel."],
    forgot:["Recuperar acesso.","Informe seu e-mail para receber um link de redefinição."],
    reset:["Nova senha.","Escolha uma senha forte para proteger sua conta."],
    "reset-sent":["Confira seu e-mail.","Se houver uma conta correspondente, enviaremos instruções de recuperação."],
    "reset-complete":["Senha atualizada.","Sua nova senha foi salva com segurança."],
  };
  return <div className="portal-auth-layout merchant-access">
    <aside className="portal-auth-brand merchant-aside">
      <Brand/>
      <div className="portal-auth-text">
        <span className="portal-eyebrow">FIDELIDADE INTELIGENTE</span>
        <h1>Clientes voltam.<br/><em>Sua loja cresce.</em></h1>
        <p>Transforme compras em relacionamento, com benefícios que respeitam a margem do negócio.</p>
        <div className="portal-auth-features">
          <span><ShieldCheck size={18}/> Seu programa, no seu ritmo</span>
          <span><Gift size={18}/> Conecte a Nuvemshop quando quiser</span>
          <span><CheckCircle2 size={18}/> Preparado para novos canais de venda</span>
        </div>
      </div>
      <span className="portal-auth-foot">VIDALYS FIDELIZA • AMBIENTE DE HOMOLOGAÇÃO</span>
    </aside>
    <main className="portal-login-panel">
      <div className="portal-login-card merchant-login-card">
        <div className="portal-login-icon"><KeyRound size={24}/></div>
        <span className="portal-eyebrow">ACESSO À PLATAFORMA</span>
        <h2>{headings[view][0]}</h2>
        <p>{headings[view][1]}</p>
        {activeAccount&&<div className="merchant-info" role="status">
          <ShieldCheck size={19}/>
          <p>Existe outra sessão aberta: <strong>{activeAccount}</strong>.
            {view==="confirm"
              ? " Ao confirmar o e-mail, você entrará na nova conta. A sessão anterior será substituída."
              : " Esta operação pertence ao link aberto, não à conta atualmente conectada."}
          </p>
          <button type="button" className="merchant-text-btn"
            disabled={pending||busy} onClick={()=>void switchAccount()}>
            Sair da sessão atual
          </button>
        </div>}
        {(error||authError&&view==="login")&&<div className="portal-auth-error" role="alert">{error||(view==="login"?authError:"")}</div>}
        {message&&<div className="merchant-success" role="status">{message}</div>}
        {view==="await-email"||view==="reset-sent"||view==="reset-complete" ? <div className="merchant-info">
          <Mail size={22}/><strong>Proteja sua conta</strong>
          {view!=="reset-complete"&&<p>Confira também a pasta de spam. O link expira em 30 minutos.</p>}
          {view==="await-email"&&<p>O cadastro não dispara outro e-mail quando a conta já está confirmada ou existe uma solicitação pendente. Aguarde um minuto antes de tentar reenviar.</p>}
          {view==="await-email"&&<>
            <button type="button" className="merchant-text-btn"
              onClick={()=>void resend()} disabled={pending}>Reenviar confirmação</button>
            <button type="button" className="merchant-text-btn"
              onClick={()=>go("forgot")}>Já tenho conta: recuperar acesso</button>
          </>}
          <button type="button" className="merchant-text-btn" onClick={()=>go("login")}>
            {activeAccount?"Voltar à conta conectada":"Voltar ao login"}
          </button>
        </div> :
        <form onSubmit={event=>void submit(event)}>
          {view==="signup"&&<>
            <label htmlFor="merchant-name">Seu nome</label>
            <input id="merchant-name" value={name} onChange={e=>setName(e.target.value)}
              autoComplete="name" required minLength={2} maxLength={100} placeholder="Como podemos chamar você?"/>
            <label htmlFor="merchant-store">Nome da loja</label>
            <input id="merchant-store" value={store} onChange={e=>setStore(e.target.value)}
              required minLength={2} maxLength={140} placeholder="Ex.: Ateliê Criativo"/>
          </>}
          {(view==="login"||view==="signup"||view==="forgot")&&<>
            <label htmlFor="merchant-email">E-mail</label>
            <input id="merchant-email" type="email" value={email} required autoComplete="email"
              onChange={e=>setEmail(e.target.value)} maxLength={254}
              placeholder="voce@sualoja.com.br"/>
          </>}
          {(view==="login"||view==="signup"||view==="reset")&&<>
            <label htmlFor="merchant-password">{view==="reset"?"Nova senha":"Senha"}</label>
            <div className="merchant-password">
              <input id="merchant-password" type={showPassword?"text":"password"} value={password}
                onChange={e=>setPassword(e.target.value)}
                autoComplete={view==="login"?"current-password":"new-password"}
                minLength={view==="login"?undefined:12} required placeholder="Sua senha"/>
              <button type="button" onClick={()=>setShowPassword(value=>!value)}
                aria-label={showPassword?"Ocultar senha":"Mostrar senha"}>
                {showPassword?<EyeOff size={18}/>:<Eye size={18}/>}
              </button>
            </div>
          </>}
          {(view==="signup"||view==="reset")&&<>
            <label htmlFor="merchant-confirm">Confirmar senha</label>
            <input id="merchant-confirm" type="password" value={confirm}
              onChange={e=>setConfirm(e.target.value)} required minLength={12}
              autoComplete="new-password" placeholder="Repita sua senha"/>
            <small className="merchant-hint">Use no mínimo 12 caracteres e uma senha exclusiva.</small>
          </>}
          {view==="login"&&<button type="button" className="merchant-forgot"
            onClick={()=>go("forgot")}>Esqueci minha senha</button>}
          <button className="portal-primary" disabled={actionBusy} type="submit">
            {actionBusy?"Processando…":
              view==="login"?"Entrar":
              view==="signup"?"Criar minha conta":
              view==="forgot"?"Enviar link de recuperação":
              view==="confirm"?"Confirmar e acessar":
              "Salvar nova senha"} <ArrowRight size={18}/>
          </button>
        </form>}
        <div className="merchant-access-nav">
          {view==="login" ? <>
            <span>Primeiro acesso?</span>
            <button type="button" onClick={()=>go("signup")}>Criar conta grátis</button>
          </> : view!=="await-email"&&view!=="reset-sent"&&view!=="reset-complete" ?
            <button type="button" onClick={()=>go("login")}>
              {activeAccount?"Voltar à conta conectada":"Voltar ao login"}
            </button>:null}
        </div>
        <div className="portal-login-help"><LockKeyhole size={16}/>
          Cadastro protegido por confirmação de e-mail. O programa não exige conexão com a Nuvemshop para começar.
        </div>
        <a href="/demo" className="portal-demo-link">Conhecer demonstração visual <ArrowRight size={15}/></a>
      </div>
    </main>
  </div>;
}
