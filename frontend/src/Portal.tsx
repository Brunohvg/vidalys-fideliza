import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight, BadgeCheck, ChartNoAxesCombined, ChevronDown, Check,
  CircleHelp, Gift, KeyRound, LayoutDashboard, LoaderCircle, LockKeyhole,
  LogOut, Menu, PackageSearch, ScanSearch, ShieldCheck, ShoppingBag, Target, UsersRound, X
} from "lucide-react";
import MarginSimulator from "./MarginSimulator";
import CampaignPlanner from "./CampaignPlanner";
import CostCatalog from "./CostCatalog";
import CatalogReconciliation from "./CatalogReconciliation";
import { ApiError, merchantApi, type CostItem, type SessionInfo, type Store } from "./api";

type Screen = "overview" | "margin" | "campaign" | "costs" | "catalog" | "roadmap";

const journey = [
  {
    title: "Defina uma margem segura",
    description: "Simule descontos, custos e limites antes de oferecer crédito.",
    state: "available", icon: ShieldCheck
  },
  {
    title: "Conecte sua Nuvemshop",
    description: "Autorização segura e prévia de produtos em teste, sem leitura de pedidos.",
    state: "future", icon: ShoppingBag
  },
  {
    title: "Crie sua primeira campanha",
    description: "Cashback, pontos e resgates entram depois da validação financeira.",
    state: "future", icon: Gift
  },
  {
    title: "Meça as recompras",
    description: "Compare custos, retenção e resultados contra uma base confiável.",
    state: "future", icon: ChartNoAxesCombined
  }
] as const;

const roleLabel: Record<Store["role"], string> = {
  owner: "Proprietário", admin: "Administrador", analyst: "Analista"
};

function Symbol({ small = false }: { small?: boolean }) {
  return <div className={"portal-symbol" + (small ? " small" : "")} aria-hidden="true">
    <svg viewBox="0 0 48 48" width={small ? 28 : 42} height={small ? 28 : 42} fill="none">
      <rect width="48" height="48" rx="14" fill="#1263FF"/>
      <path d="M12 14 24 35 36 14" stroke="#fff" strokeWidth="5.3" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M12 31c8 9 21 6 25-8" stroke="#00D1E6" strokeWidth="3" strokeLinecap="round"/>
    </svg>
  </div>;
}

function Wordmark() {
  return <span className="portal-wordmark">vidalys<span>fideliza</span></span>;
}

function StatusPill({ children }: { children: ReactNode }) {
  return <span className="portal-status"><ShieldCheck size={14}/>{children}</span>;
}

export default function Portal() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [page, setPage] = useState<Screen>(() =>
    new URLSearchParams(window.location.search).has("nuvemshop") ? "catalog" : "overview"
  );
  const [drawer, setDrawer] = useState(false);
  const [selectedId, setSelectedId] = useState<string>("");
  const [seedItem, setSeedItem] = useState<CostItem | null>(null);

  useEffect(() => {
    let current = true;
    merchantApi.getSession().then(value => {
      if (current) { setSession(value); setSessionError(""); }
    }).catch(() => {
      if (current) setSessionError("Não conseguimos conectar ao servidor. Confira a API e tente novamente.");
    });
    return () => { current = false; };
  }, [refresh]);

  const doLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthBusy(true); setAuthError("");
    try {
      await merchantApi.login(username, password);
      const value = await merchantApi.getSession();
      setPassword("");
      setSession(value);
      setPage("overview");
      setSelectedId("");
    } catch (error) {
      setAuthError(error instanceof ApiError ? error.message : "Falha de conexão. Verifique sua rede.");
    } finally {
      setAuthBusy(false);
    }
  };

  const doLogout = async () => {
    setAuthBusy(true); setAuthError("");
    try {
      await merchantApi.logout();
      setSession({ authenticated: false, user: null, tenants: [] });
      setSelectedId("");
      setPage("overview");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Não foi possível sair. Atualize a página.");
    } finally {
      setAuthBusy(false);
    }
  };

  const navigate = (next: Screen) => { setPage(next); setDrawer(false); if (next !== "margin") setSeedItem(null); };
  const simulateProduct = (item: CostItem) => { setSeedItem(item); setPage("margin"); setDrawer(false); };
  const tenants = session?.authenticated ? session.tenants : [];
  const tenant = tenants.find(value => value.id === selectedId) || tenants[0];

  if (!session) {
    return <div className="portal-loading">
      <Symbol/>
      <div><Wordmark/><p>{sessionError || "Verificando sessão segura…"}</p></div>
      {sessionError ? <button className="portal-primary" onClick={() => {setSessionError(""); setRefresh(n => n + 1);}}>Tentar novamente <ArrowRight size={17}/></button>
        : <LoaderCircle className="portal-spin" size={21} aria-label="Carregando" />}
    </div>;
  }

  if (!session.authenticated) {
    return <div className="portal-auth-layout">
      <section className="portal-auth-brand">
        <div className="portal-auth-logo"><Symbol/><Wordmark/></div>
        <div className="portal-auth-text">
          <span className="portal-eyebrow">FIDELIDADE INTELIGENTE</span>
          <h1>Clientes voltam.<br/><em>Seu lucro fica.</em></h1>
          <p>Uma plataforma para criar relacionamentos duradouros sem abrir mão da margem do seu negócio.</p>
          <div className="portal-auth-features">
            <span><Check size={18}/> Cashback com limites claros</span>
            <span><Check size={18}/> Visão financeira antes da campanha</span>
            <span><Check size={18}/> Tecnologia preparada para várias lojas</span>
          </div>
        </div>
        <span className="portal-auth-foot">VIDALYS • AMBIENTE DE HOMOLOGAÇÃO</span>
      </section>
      <section className="portal-login-panel">
        <div className="portal-login-card">
          <div className="portal-login-icon"><KeyRound size={24}/></div>
          <div className="portal-eyebrow">ACESSO À PLATAFORMA</div>
          <h2>Bem-vindo de volta.</h2>
          <p>Entre com sua conta de lojista para acessar suas ferramentas.</p>
          <form onSubmit={doLogin}>
            <label htmlFor="portal-username">Usuário</label>
            <input id="portal-username" value={username} autoComplete="username" required
              onChange={e=>setUsername(e.target.value)} placeholder="Seu usuário"/>
            <label htmlFor="portal-password">Senha</label>
            <input id="portal-password" type="password" value={password} autoComplete="current-password" required
              onChange={e=>setPassword(e.target.value)} placeholder="Sua senha"/>
            {authError && <div className="portal-auth-error" role="alert">{authError}</div>}
            <button className="portal-primary" disabled={authBusy} type="submit">
              {authBusy ? "Entrando…" : "Acessar minha loja"} <ArrowRight size={18}/>
            </button>
          </form>
          <div className="portal-login-help"><LockKeyhole size={16}/>
            Contas são criadas pelo administrador nesta fase. Nenhum acesso público está liberado.
          </div>
          <a href="/demo" className="portal-demo-link">Conhecer demonstração visual <ArrowRight size={15}/></a>
        </div>
      </section>
    </div>;
  }

  return <div className="portal-shell">
    <aside className={"portal-side" + (drawer ? " is-open" : "")} aria-label="Menu do lojista">
      <div className="portal-side-brand"><Symbol small/><Wordmark/><button className="portal-mobile-close" onClick={()=>setDrawer(false)} aria-label="Fechar menu"><X size={21}/></button></div>
      <div className="portal-store">
        <div className="portal-store-mark"><ShoppingBag size={18}/></div>
        <div><strong>{tenant?.name || "Nenhuma loja"}</strong><span>{tenant ? roleLabel[tenant.role] : "Sem vínculo"}</span></div>
      </div>
      <div className="portal-nav-caption">MENU PRINCIPAL</div>
      <nav className="portal-nav">
        <button onClick={()=>navigate("overview")} className={page==="overview"?"is-active":""}><LayoutDashboard size={19}/> Visão geral</button>
        <button onClick={()=>navigate("margin")} className={page==="margin"?"is-active":""}><ShieldCheck size={19}/> Rentabilidade</button>
        <button onClick={()=>navigate("campaign")} className={page==="campaign"?"is-active":""}><Target size={19}/> Planejamento <span>Beta</span></button>
        <button onClick={()=>navigate("costs")} className={page==="costs"?"is-active":""}><PackageSearch size={19}/> Custos por SKU</button>
        <button onClick={()=>navigate("catalog")} className={page==="catalog"?"is-active":""}><ScanSearch size={19}/> Conciliação <span>Prévia</span></button>
        <button onClick={()=>navigate("roadmap")} className={page==="roadmap"?"is-active":""}><Gift size={19}/> Programas <span>Em breve</span></button>
      </nav>
      <div className="portal-side-bottom">
        <div className="portal-side-guide"><CircleHelp size={21}/><b>Primeiro, controle a margem.</b><p>Simule benefícios antes de investir em cashback.</p><button onClick={()=>navigate("margin")}>Abrir simulador <ArrowRight size={16}/></button></div>
        <button className="portal-signout" disabled={authBusy} onClick={doLogout}><LogOut size={18}/> Sair da conta</button>
      </div>
    </aside>
    {drawer && <button aria-label="Fechar navegação" className="portal-overlay" onClick={()=>setDrawer(false)}/>}
    <div className="portal-main">
      <header className="portal-top">
        <div className="portal-top-title"><button onClick={()=>setDrawer(true)} className="portal-menu" aria-label="Abrir menu"><Menu size={23}/></button>
          <span>Plataforma</span><span className="portal-breadcrumb">/</span><strong>{page==="overview"?"Visão geral":page==="margin"?"Rentabilidade":page==="campaign"?"Planejamento":page==="costs"?"Custos por SKU":page==="catalog"?"Conciliação":"Programas"}</strong>
        </div>
        <div className="portal-top-right"><span className="portal-test-label"><span/> HOMOLOGAÇÃO</span><span className="portal-avatar">{session.user.display_name.slice(0,2).toUpperCase()}</span></div>
      </header>
      <main className="portal-content">
        <div className="portal-content-head">
          <div><span className="portal-eyebrow">CENTRO DE FIDELIDADE</span>
            <h1>{page==="overview"?"O próximo passo da sua loja.":page==="margin"?"Inteligência de margem.":page==="campaign"?"Planeje antes de recompensar.":page==="costs"?"Conheça o custo antes do benefício.":page==="catalog"?"Valide variantes antes de importar.":"Programas de fidelidade."}</h1>
            <p>{page==="overview"?"Comece pelo que importa: criar benefícios sustentáveis para o seu negócio.":page==="margin"?"Simule os custos e peça uma análise ao servidor da loja.":page==="campaign"?"Teste o orçamento e os riscos de uma campanha com números claros.":page==="costs"?"Registre custos por item, confira sua origem e simule sem comprometer a margem.":page==="catalog"?"Compare uma amostra JSON do catálogo com os custos da loja, sem gravar nada.":"Preparando um motor de pontos e cashback seguro."}</p>
          </div>
          <StatusPill>Ambiente de teste</StatusPill>
        </div>

        {tenants.length===0 ? <section className="portal-empty panel">
            <UsersRound size={36}/><h2>Sua conta ainda não tem loja vinculada</h2>
            <p>Peça a um administrador que crie uma loja e associe seu usuário no Django Admin. Nenhuma loja ou credencial é criada automaticamente.</p>
            <button onClick={doLogout} className="portal-secondary">Trocar de conta</button>
          </section> : <>
            <div className="portal-tenant-bar"><label htmlFor="portal-tenant">Loja selecionada</label>
              <div className="portal-select-wrap"><select id="portal-tenant" value={tenant.id} onChange={e=>{setSelectedId(e.target.value);setSeedItem(null);setPage("overview");}}>
                {tenants.map(t=><option key={t.id} value={t.id}>{t.name} · {roleLabel[t.role]}</option>)}
              </select><ChevronDown size={17}/></div>
              {tenant.status!=="active" && <span className="portal-unlinked">Cadastro {tenant.status==="draft"?"em preparação":"suspenso"}</span>}
            </div>
            {page==="overview" && <div className="portal-home">
              <section className="portal-welcome">
                <div><span className="portal-welcome-label"><BadgeCheck size={17}/> SUA LOJA, SEU CONTROLE</span>
                  <h2>Fidelidade que respeita <em>seus números.</em></h2>
                  <p>O próximo benefício não precisa começar com um desconto. Descubra primeiro quanto sua loja pode oferecer.</p>
                  <div className="portal-welcome-actions">
                    <button className="portal-primary" onClick={()=>navigate("margin")}>Simular minha margem <ArrowRight size={18}/></button>
                    <button className="portal-welcome-secondary" onClick={()=>navigate("campaign")}>Planejar campanha <Target size={17}/></button>
                    <button className="portal-welcome-secondary" onClick={()=>navigate("costs")}>Custos por SKU <PackageSearch size={17}/></button>
                    <button className="portal-welcome-secondary" onClick={()=>navigate("catalog")}>Prévia de catálogo <ScanSearch size={17}/></button>
                  </div>
                </div><div className="portal-welcome-icon" aria-hidden="true"><ShieldCheck size={64} strokeWidth={1.3}/></div>
              </section>
              <div className="portal-home-grid">
                <section className="portal-panel">
                  <div className="portal-panel-header"><div><span className="portal-eyebrow">INÍCIO RÁPIDO</span><h2>Sua jornada de fidelidade</h2></div><span className="portal-phase">4 etapas</span></div>
                  <div className="portal-steps">{journey.map((item,index)=>{
                    const Icon=item.icon;
                    return <div className="portal-step" key={item.title}><span className={"portal-step-icon "+item.state}><Icon size={20}/></span><div><strong>{index+1}. {item.title}</strong><p>{item.description}</p></div><span className={"portal-step-state "+item.state}>{item.state==="available"?"Disponível":"Em desenvolvimento"}</span></div>;
                  })}</div>
                </section>
                <section className="portal-panel portal-summary">
                  <span className="portal-eyebrow">STATUS ATUAL</span><div className="portal-progress-graphic"><ShieldCheck size={30}/></div>
                  <h2>Fundação protegida.</h2><p>Seu espaço está isolado das outras lojas. Não há campanhas, créditos ou compras reais conectadas.</p>
                  <div className="portal-fact"><span>Loja</span><strong>{tenant.name}</strong></div>
                  <div className="portal-fact"><span>Acesso</span><strong>{roleLabel[tenant.role]}</strong></div>
                  <div className="portal-fact"><span>Integração Nuvemshop</span><strong>Consultar na Conciliação</strong></div>
                  <button onClick={()=>navigate("margin")} className="portal-text-action">Abrir inteligência de margem <ArrowRight size={16}/></button>
                </section>
              </div>
            </div>}
            {page==="margin" && <MarginSimulator tenantId={tenant.id} initialItem={seedItem} key={tenant.id+":"+(seedItem?.id||"")}/>}
            {page==="costs" && <CostCatalog tenantId={tenant.id} role={tenant.role} onSimulate={simulateProduct} key={tenant.id}/>}
            {page==="catalog" && <CatalogReconciliation tenantId={tenant.id} role={tenant.role} key={tenant.id}/>}
            {page==="campaign" && <CampaignPlanner tenantId={tenant.id} key={tenant.id}/>}
            {page==="roadmap" && <section className="portal-panel portal-coming">
              <Gift size={37}/><h2>Programas, do jeito certo.</h2>
              <p>O próximo módulo trará regras de cashback, pontos, reservas e resgate após a validação do checkout. Nenhum benefício será ativado sem autorização do lojista.</p>
              <button className="portal-primary" onClick={()=>navigate("margin")}>Começar pelo simulador <ArrowRight size={16}/></button>
            </section>}
          </>}
        {authError && <div className="portal-auth-error" role="alert">{authError}</div>}
        <footer className="portal-footer"><LockKeyhole size={14}/> Vidalys Fideliza · Homologação · Nenhuma ação executada na loja conectada</footer>
      </main>
    </div>
  </div>;
}
