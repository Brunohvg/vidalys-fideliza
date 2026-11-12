import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight, ChevronDown, Check,
  Gift, KeyRound, LayoutDashboard, LoaderCircle, LockKeyhole,
  LogOut, Menu, PackageSearch, ScanSearch, ShieldCheck, ShoppingBag, Target, UsersRound, X, BarChart3, HeartHandshake, Settings2
} from "lucide-react";
import MarginSimulator from "./MarginSimulator";
import CampaignGuide from "./CampaignGuide";
import ParticipantsBoard from "./ParticipantsBoard";
import StoreSettings from "./StoreSettings";
import ActionCenter from "./ActionCenter";
import CostCatalog from "./CostCatalog";
import CatalogReconciliation from "./CatalogReconciliation";
import { ApiError, merchantApi, type CostItem, type SessionInfo, type Store } from "./api";

type Screen = "overview" | "clients" | "campaign" | "results" | "margin" | "costs" | "catalog" | "roadmap" | "settings";

const roleLabel: Record<Store["role"], string> = {
  owner: "Proprietário", admin: "Administrador", analyst: "Analista"
};

function Symbol({ small = false }: { small?: boolean }) {
  return <div className={"portal-symbol" + (small ? " small" : "")} aria-hidden="true">
    <svg viewBox="0 0 48 48" width={small ? 28 : 42} height={small ? 28 : 42} fill="none">
      <rect width="48" height="48" rx="14" fill="#087F79"/>
      <path d="M12 14 24 35 36 14" stroke="#fff" strokeWidth="5.3" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M12 31c8 9 21 6 25-8" stroke="#37D5BB" strokeWidth="3" strokeLinecap="round"/>
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
  const [compactMenu, setCompactMenu] = useState(() =>
    window.matchMedia("(max-width: 1020px)").matches
  );
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeMenuRef = useRef<HTMLButtonElement>(null);
  const sideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1020px)");
    const sync = () => { setCompactMenu(mq.matches); setDrawer(false); };
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!compactMenu || !drawer) return;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeMenuRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawer(false);
        menuButtonRef.current?.focus();
      } else if (event.key === "Tab") {
        const items = Array.from(sideRef.current?.querySelectorAll<HTMLButtonElement>(
          "button:not(:disabled)"
        ) || []);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = oldOverflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [drawer, compactMenu]);
  const closeDrawer = () => {
    setDrawer(false);
    if (compactMenu) menuButtonRef.current?.focus();
  };
  const [selectedId, setSelectedId] = useState<string>(() =>
    new URLSearchParams(window.location.search).get("nuvemshop_tenant") || ""
  );
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
          <h1>Mais conexão.<br/><em>Mais motivos para voltar.</em></h1>
          <p>Uma experiência simples para fortalecer a recompra, acompanhar benefícios e tomar decisões responsáveis.</p>
          <div className="portal-auth-features">
            <span><Check size={18}/> Benefícios planejados com limites claros</span>
            <span><Check size={18}/> Campanhas guiadas e transparentes</span>
            <span><Check size={18}/> Relacionamento com clientes como prioridade</span>
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
    <aside id="portal-sidebar" ref={sideRef} className={"portal-side" + (drawer ? " is-open" : "")} aria-label="Menu do lojista" aria-hidden={compactMenu && !drawer} inert={compactMenu && !drawer}>
      <div className="portal-side-brand"><Symbol small/><Wordmark/><button ref={closeMenuRef} className="portal-mobile-close" onClick={closeDrawer} aria-label="Fechar menu"><X size={21}/></button></div>
      <div className="portal-store">
        <div className="portal-store-mark"><ShoppingBag size={18}/></div>
        <div><strong>{tenant?.name || "Nenhuma loja"}</strong><span>{tenant ? roleLabel[tenant.role] : "Sem vínculo"}</span></div>
      </div>
      <div className="portal-nav-caption">MENU PRINCIPAL</div>
      <nav className="portal-nav">
        <button onClick={()=>navigate("overview")} className={page==="overview"?"is-active":""}><LayoutDashboard size={19}/> Visão geral</button>
        <button onClick={()=>navigate("clients")} className={page==="clients"?"is-active":""}><UsersRound size={19}/> Clientes</button>
        <button onClick={()=>navigate("campaign")} className={page==="campaign"?"is-active":""}><Gift size={19}/> Campanhas <span>Prévia</span></button>
        <button onClick={()=>navigate("results")} className={page==="results"?"is-active":""}><BarChart3 size={19}/> Resultados</button>
      </nav>
      <div className="portal-nav-caption portal-tools-caption">FERRAMENTAS AVANÇADAS</div>
      <nav className="portal-nav portal-nav-secondary">
        <button onClick={()=>navigate("margin")} className={page==="margin"?"is-active":""}><ShieldCheck size={19}/> Rentabilidade</button>
        <button onClick={()=>navigate("costs")} className={page==="costs"?"is-active":""}><PackageSearch size={19}/> Custos por SKU</button>
        <button onClick={()=>navigate("catalog")} className={page==="catalog"?"is-active":""}><ScanSearch size={19}/> Conciliação</button>
        <button onClick={()=>navigate("roadmap")} className={page==="roadmap"?"is-active":""}><Target size={19}/> Motor de benefícios <span>Em breve</span></button>

      </nav>
      <nav className="portal-nav portal-nav-secondary ss-settings-menu" aria-label="Preferências da loja">
        <button onClick={()=>navigate("settings")} className={page==="settings"?"is-active":""}>
          <Settings2 size={19}/> Configurações
        </button>
      </nav>
      <div className="portal-side-bottom">
        <div className="portal-side-guide"><HeartHandshake size={21}/><b>Comece pela recompra.</b><p>Desenhe sua campanha em três passos. A análise financeira está nas ferramentas.</p><button onClick={()=>navigate("campaign")}>Criar prévia <ArrowRight size={16}/></button></div>
        <button className="portal-signout" disabled={authBusy} onClick={doLogout}><LogOut size={18}/> Sair da conta</button>
      </div>
    </aside>
    {compactMenu && drawer && <button aria-label="Fechar navegação" className="portal-overlay" onClick={closeDrawer}/>}
    <div className="portal-main">
      <header className="portal-top">
        <div className="portal-top-title"><button onClick={()=>setDrawer(true)} ref={menuButtonRef} className="portal-menu" aria-label="Abrir menu" aria-controls="portal-sidebar" aria-expanded={compactMenu && drawer}><Menu size={23}/></button>
          <span>Plataforma</span><span className="portal-breadcrumb">/</span><strong>{page==="overview"?"Visão geral":page==="clients"?"Clientes":page==="campaign"?"Campanhas":page==="results"?"Resultados":page==="margin"?"Rentabilidade":page==="costs"?"Custos por SKU":page==="catalog"?"Conciliação":page==="settings"?"Configurações":"Motor de benefícios"}</strong>
        </div>
        <div className="portal-top-right"><span className="portal-test-label"><span/> HOMOLOGAÇÃO</span><span className="portal-avatar">{session.user.display_name.slice(0,2).toUpperCase()}</span></div>
      </header>
      <main className="portal-content">
        <div className="portal-content-head">
          <div><span className="portal-eyebrow">CENTRO DE FIDELIDADE</span>
            <h1>{page==="overview"?"O próximo passo da sua loja.":page==="clients"?"Seu relacionamento com clientes.":page==="campaign"?"Uma campanha em poucos passos.":page==="results"?"Resultados que importam.":page==="margin"?"Inteligência de margem.":page==="costs"?"Conheça o custo antes do benefício.":page==="catalog"?"Valide variantes antes de importar.":page==="settings"?"Sua loja, do seu jeito.":"Motor de benefícios."}</h1>
            <p>{page==="overview"?"Ações práticas e transparentes para fortalecer a recompra.":page==="clients"?"Acompanhe adesões verificadas, sem confundir compradores com participantes.":page==="campaign"?"Escolha um objetivo e revise o orçamento antes de agir.":page==="results"?"Acompanhe recompra e retorno quando houver eventos confiáveis.":page==="margin"?"Simule os custos e peça uma análise ao servidor da loja.":page==="costs"?"Cadastro manual complementar quando o custo não vem da loja.":page==="catalog"?"Valide variantes e custos antes de importar.":page==="settings"?"Personalize a identidade do programa e confira a situação das integrações.":"Preparando um motor de pontos e cashback seguro."}</p>
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
            {page==="overview" && <ActionCenter tenantId={tenant.id} key={tenant.id}
              onNavigate={destination=>navigate(destination)}/>}
            {page==="clients" && <ParticipantsBoard tenantId={tenant.id} role={tenant.role} storeSlug={tenant.slug} tenantStatus={tenant.status} key={tenant.id}/>}
            {page==="settings" && <StoreSettings tenantId={tenant.id} role={tenant.role}
              onGoToClients={()=>navigate("clients")} key={tenant.id}/>}
            {page==="results" && <section className="xp-panel xp-results-empty">
              <div className="xp-results-icon"><BarChart3 size={40}/></div>
              <span className="portal-eyebrow">MÉTRICAS VERIFICÁVEIS</span>
              <h2>Resultados sem números inventados.</h2>
              <p>Quando o programa registrar adesões, benefícios concedidos e resgates, esta área mostrará participantes ativos, recompras verificadas e custo de fidelização. Nenhum pedido ou faturamento é atribuído ao Fideliza apenas por coincidência.</p>
              <button className="portal-primary" onClick={()=>navigate("campaign")}>Explorar campanha <ArrowRight size={17}/></button>
            </section>}
            {page==="margin" && <MarginSimulator tenantId={tenant.id} initialItem={seedItem} key={tenant.id+":"+(seedItem?.id||"")}/>}
            {page==="costs" && <CostCatalog tenantId={tenant.id} role={tenant.role} onSimulate={simulateProduct} key={tenant.id}/>}
            {page==="catalog" && <CatalogReconciliation tenantId={tenant.id} role={tenant.role} key={tenant.id}/>}
            {page==="campaign" && <CampaignGuide tenantId={tenant.id} role={tenant.role} key={tenant.id}/>}
            {page==="roadmap" && <section className="portal-panel portal-coming">
              <Gift size={37}/><h2>Programas, do jeito certo.</h2>
              <p>O motor futuro fará o registro, concessão, reserva, resgate e estorno de benefícios com trilha de auditoria. Nenhum crédito é concedido nesta etapa.</p>
              <button className="portal-primary" onClick={()=>navigate("campaign")}>Começar pelo planejamento <ArrowRight size={16}/></button>
            </section>}
          </>}
        {authError && <div className="portal-auth-error" role="alert">{authError}</div>}
        <footer className="portal-footer"><LockKeyhole size={14}/> Vidalys Fideliza · Homologação · Nenhuma ação executada na loja conectada</footer>
      </main>
    </div>
  </div>;
}
