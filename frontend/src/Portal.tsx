import { useEffect, useRef, useState } from "react";
import {
  ArrowRight, ChevronDown,
  Gift, LayoutDashboard, LoaderCircle,
  LogOut, Menu, PackageSearch, ScanSearch, ShieldCheck, ShoppingBag, UsersRound, X, BarChart3, HeartHandshake, Settings2
} from "lucide-react";
import BenefitCostOverview from "./BenefitCostOverview";
import MerchantAccess from "./MerchantAccess";
import CampaignGuide from "./CampaignGuide";
import ParticipantsBoard from "./ParticipantsBoard";
import ProgramHub, { type ProgramArea } from "./ProgramHub";
import SalesWorkspace from "./SalesWorkspace";
import StoreSettings from "./StoreSettings";
import ActionCenter from "./ActionCenter";
import ResultsOverview from "./ResultsOverview";
import CostCatalog from "./CostCatalog";
import CatalogReconciliation from "./CatalogReconciliation";
import { ApiError, merchantApi, type CostItem, type SessionInfo, type Store } from "./api";
import { merchantPaths, merchantScreenForPath, type MerchantScreen } from "./routes";

type Screen = MerchantScreen;

// Links de conta são rotas públicas mesmo com OUTRO lojista autenticado.
// A ação só troca a sessão quando a confirmação explícita for concluída.
const isMerchantAuthPage = (path: string) =>
  ["/confirmar-conta", "/redefinir-senha", "/cadastrar", "/esqueci-senha"]
    .includes(path.replace(/\/+$/, "") || "/");

const roleLabel: Record<Store["role"], string> = {
  owner: "Proprietário", admin: "Administrador", analyst: "Analista"
};

// Menu único, agrupado por intenção. Nada escondido em "mais ferramentas".
type NavItem = { page: Screen; label: string; Icon: typeof Gift; badge?: string };
const navGroups: { caption: string | null; items: NavItem[] }[] = [
  { caption: null, items: [{ page: "overview", label: "Início", Icon: LayoutDashboard }] },
  { caption: "PROGRAMA", items: [
    { page: "program", label: "Clube", Icon: HeartHandshake },
    { page: "campaign", label: "Campanhas", Icon: Gift, badge: "Prévia" }] },
  { caption: "OPERAÇÃO", items: [
    { page: "clients", label: "Clientes", Icon: UsersRound },
    { page: "sales", label: "Vendas", Icon: ShoppingBag }] },
  { caption: "ANÁLISE", items: [
    { page: "results", label: "Resultados", Icon: BarChart3 },
    { page: "margin", label: "Custo dos benefícios", Icon: ShieldCheck }] },
  { caption: "AJUSTES", items: [
    { page: "settings", label: "Configurações", Icon: Settings2 },
    { page: "costs", label: "Custos dos produtos", Icon: PackageSearch },
    { page: "catalog", label: "Conciliação", Icon: ScanSearch }] },
];
const navItems = navGroups.flatMap(group => group.items.map(item => ({ ...item, caption: group.caption })));

function Symbol({ small = false }: { small?: boolean }) {
  return <img src="/brand-mark.svg" width={small ? 28 : 42} height={small ? 28 : 42} alt="" aria-hidden="true" />;
}

function Wordmark() {
  return <span className="portal-wordmark">vidalys<span>fideliza</span></span>;
}

export default function Portal() {
  const [programArea, setProgramArea] = useState<ProgramArea>("rewards");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [authRoute, setAuthRoute] = useState(() => isMerchantAuthPage(window.location.pathname));

  useEffect(() => {
    const syncRoute = () => {
      setAuthRoute(isMerchantAuthPage(window.location.pathname));
      const route = merchantScreenForPath(window.location.pathname);
      if (route) {
        setPage(route);
        setSeedItem(null);
        setDrawer(false);
      }
    };
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, []);

  const [refresh, setRefresh] = useState(0);
   const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [page, setPage] = useState<Screen>(() =>
    new URLSearchParams(window.location.search).has("nuvemshop")
      ? "settings" : merchantScreenForPath(window.location.pathname) || "overview"
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
    // Abrir o foco somente depois de reabilitar controles invisíveis.
    sideRef.current?.removeAttribute("inert");
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
  useEffect(() => {
    // O sidebar monta APÓS a sessão: reavaliar o atributo no login.
    const el = sideRef.current;
    if (!el) return;
    if (compactMenu && !drawer) el.setAttribute("inert", "");
    else el.removeAttribute("inert");
  }, [compactMenu, drawer, session?.authenticated]);

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
      if (current) {
        if (value.authenticated && window.location.pathname === "/entrar") {
          window.history.replaceState(null, "", "/app/visao-geral");
        }
        setSession(value);setSessionError("");
      }
    }).catch(() => {
      if (current) setSessionError("Não conseguimos conectar ao servidor. Confira a API e tente novamente.");
    });
    return () => { current = false; };
  }, [refresh]);

  const doLogin = async (email:string,password:string) => {
    setAuthBusy(true); setAuthError("");
    try {
      await merchantApi.login(email, password);
      const value = await merchantApi.getSession();
      setSession(value);
      // Um acesso iniciado em /entrar termina na área autenticada.
      // Deep links /app/* continuam preservados.
      if (window.location.pathname === "/entrar" || window.location.pathname === "/cadastrar") {
        window.history.replaceState(null, "", "/app/visao-geral");
      }
      setAuthRoute(false);
      setPage(merchantScreenForPath(window.location.pathname) || "overview");
      setSelectedId("");
    } catch (error) {
      setAuthError(error instanceof ApiError ? error.message : "Falha de conexão. Verifique sua rede.");
    } finally {
      setAuthBusy(false);
    }
  };
  const afterEmailConfirmation = async () => {
    const value=await merchantApi.getSession();
    if(!value.authenticated || value.tenants.length === 0)
      throw new Error("Cadastro confirmado, mas a empresa não apareceu na sessão. Contate o suporte.");
    // Somente depois do backend confirmar o token e autenticar a nova conta.
    window.history.replaceState(null, "", "/app/visao-geral");
    setAuthRoute(false);
    setSession(value);setAuthError("");setPage("overview");setSelectedId("");
  };

  const switchAccount = async () => {
    // Não encerrar a sessão anterior apenas por abrir um link recebido por e-mail.
    // Encerramento acontece quando a pessoa escolhe explicitamente trocar conta.
    await merchantApi.logout();
    setSession({ authenticated: false, user: null, tenants: [] });
    setSelectedId("");
    setPage("overview");
    setAuthError("");
  };

  const doLogout = async () => {
    setAuthBusy(true); setAuthError("");
    try {
      await merchantApi.logout();
      window.history.replaceState(null, "", "/entrar");
      setSession({ authenticated: false, user: null, tenants: [] });
      setSelectedId("");
      setPage("overview");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Não foi possível sair. Atualize a página.");
    } finally {
      setAuthBusy(false);
    }
  };

  const navigate = (next: Screen, area?: ProgramArea) => {
    setProgramArea(area ?? "rewards");
    if (window.location.pathname !== merchantPaths[next]) {
      window.history.pushState(null, "", merchantPaths[next]);
    }
    setPage(next);
    setDrawer(false);
    if (compactMenu && drawer) menuButtonRef.current?.focus();
    if (next !== "margin") setSeedItem(null);
  };
  const simulateProduct = (item: CostItem) => {
    setSeedItem(item); navigate("margin");
  };
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

  if (!session.authenticated || authRoute) {
    return <MerchantAccess
      onLogin={doLogin}
      onVerified={afterEmailConfirmation}
      onSwitchAccount={switchAccount}
      onNavigate={path => setAuthRoute(isMerchantAuthPage(path))}
      activeAccount={session.authenticated ? session.user.display_name : null}
      busy={authBusy} authError={authError}/>;
  }

  return <div className="portal-shell loyalty-merchant">
    <aside id="portal-sidebar" ref={sideRef} className={"portal-side" + (drawer ? " is-open" : "")} aria-label="Menu do lojista" aria-hidden={compactMenu && !drawer}>
      <div className="portal-side-brand"><img className="loyalty-merchant-logo" src="/brand-logo-white.svg" alt="Vidalys Fideliza" width={178} height={48}/><button ref={closeMenuRef} className="portal-mobile-close" onClick={closeDrawer} aria-label="Fechar menu"><X size={21}/></button></div>
      {tenant ? <div className="portal-store">
        <div className="portal-store-mark"><ShoppingBag size={18}/></div>
        <div className="portal-store-switch">
          <label htmlFor="portal-tenant" className="portal-sr">Loja selecionada</label>
          <select id="portal-tenant" value={tenant.id} onChange={e=>{setSelectedId(e.target.value);setSeedItem(null);setPage("overview");}}>
            {tenants.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          {tenants.length>1 && <ChevronDown size={15} aria-hidden="true"/>}
          <span>{roleLabel[tenant.role]}{tenant.status!=="active" && " · "+(tenant.status==="draft"?"cadastro em preparação":"suspensa")}</span>
        </div>
      </div> : <div className="portal-store">
        <div className="portal-store-mark"><ShoppingBag size={18}/></div>
        <div><strong>Nenhuma loja</strong><span>Sem vínculo</span></div>
      </div>}
      {navGroups.map(group => <div className="portal-nav-group" key={group.caption ?? "inicio"}>
        {group.caption && <div className="portal-nav-caption">{group.caption}</div>}
        <nav className="portal-nav" aria-label={group.caption ? "Menu " + group.caption.toLowerCase() : "Menu principal"}>
          {group.items.map(({ page: target, label, Icon, badge }) => <button key={target} onClick={()=>navigate(target)}
            className={page===target?"is-active":""} aria-current={page===target?"page":undefined}>
            <Icon size={19}/> {label}{badge && <span>{badge}</span>}</button>)}
        </nav>
      </div>)}
      <div className="portal-side-bottom">
        <button className="portal-signout" disabled={authBusy} onClick={doLogout}><LogOut size={18}/> Sair da conta</button>
      </div>
    </aside>
    {compactMenu && drawer && <button aria-label="Fechar navegação" className="portal-overlay" onClick={closeDrawer}/>}
    <div className="portal-main">
      <header className="portal-top">
        <div className="portal-top-title"><button onClick={()=>setDrawer(true)} ref={menuButtonRef} className="portal-menu" aria-label="Abrir menu" aria-controls="portal-sidebar" aria-expanded={compactMenu && drawer}><Menu size={23}/></button>
          <span>{navItems.find(item => item.page === page)?.caption?.toLowerCase().replace(/^./, c => c.toUpperCase()) ?? "Painel"}</span><span className="portal-breadcrumb">/</span><strong>{navItems.find(item => item.page === page)?.label ?? "Início"}</strong>
        </div>
        <div className="portal-top-right"><span className="portal-test-label"><span/> HOMOLOGAÇÃO</span><span className="portal-avatar">{session.user.display_name.slice(0,2).toUpperCase()}</span></div>
      </header>
      <main className="portal-content">
        <div className="portal-content-head">
          <div>
            <h1>{page==="overview"?"O próximo passo da sua loja.":page==="program"?"Seu programa de fidelidade.":page==="clients"?"Participantes do clube.":page==="sales"?"Pedidos e vendas.":page==="campaign"?"Uma campanha em poucos passos.":page==="results"?"Resultados que importam.":page==="margin"?"Quanto custa meu programa?":page==="costs"?"Conheça o custo antes do benefício.":page==="catalog"?"Valide variantes antes de importar.":page==="settings"?"Sua loja, do seu jeito.":"Motor de benefícios."}</h1>
            <p>{page==="overview"?"Ações práticas e transparentes para fortalecer a recompra.":page==="program"?"Recompensas, regra de pontos e participantes — uma área de cada vez.":page==="clients"?"Consulte quem aderiu ao clube e a situação de cada participação.":page==="sales"?"Acompanhe os pedidos da Nuvemshop e registre vendas presenciais sem duplicar compras.":page==="campaign"?"Escolha um objetivo e revise o orçamento antes de agir.":page==="results"?"Acompanhe recompra e retorno quando houver eventos confiáveis.":page==="margin"?"Entenda o custo dos benefícios antes de publicá-los.":page==="costs"?"Cadastro manual complementar quando o custo não vem da loja.":page==="catalog"?"Valide variantes e custos antes de importar.":page==="settings"?"Personalize a identidade do programa e confira a situação das integrações.":"Preparando um motor de pontos e cashback seguro."}</p>
          </div>
        </div>

        {tenants.length===0 ? <section className="portal-empty panel">
            <UsersRound size={36}/><h2>Sua conta está ativa, mas sem empresa associada</h2>
            <p>Seu acesso funciona, porém nenhuma loja foi atribuída a esta conta. Se você confirmou o cadastro pelo e-mail, a empresa deveria aparecer automaticamente. Antes de criar outra conta, solicite a revisão do vínculo ao suporte.</p>
            <p>Contas técnicas criadas no Django Admin não recebem loja automaticamente. Um administrador pode verificar a empresa em Empresas → Lojas e seus vínculos, sem associar usuários apenas pelo nome ou e-mail.</p>
            <button onClick={doLogout} className="portal-secondary">Trocar de conta</button>
          </section> : <>
            {page==="overview" && <ActionCenter tenantId={tenant.id} role={tenant.role} platform={tenant.platform} key={tenant.id}
              onNavigate={(destination, area)=>navigate(destination, area)}/>}
            {page==="program" && <ProgramHub tenantId={tenant.id} role={tenant.role} storeSlug={tenant.slug} tenantStatus={tenant.status} platform={tenant.platform} initialArea={programArea} onViewClients={()=>navigate("clients")} onViewSales={()=>navigate("sales")} onOpenSettings={()=>navigate("settings")} key={tenant.id+":"+programArea}/>}
            {page==="clients" && <ParticipantsBoard tenantId={tenant.id} onOpenProgram={()=>navigate("program", "participants")} key={tenant.id}/>}
            {page==="sales" && <SalesWorkspace tenantId={tenant.id} role={tenant.role} key={tenant.id}/>}
            {page==="settings" && <StoreSettings tenantId={tenant.id} role={tenant.role}
              onGoToProgram={()=>navigate("program")} key={tenant.id}/>}
            {page==="results" && <ResultsOverview tenantId={tenant.id}
              onClients={()=>navigate("clients")} onSales={()=>navigate("sales")}
              onProgram={()=>navigate("program")} key={tenant.id}/>}
            {page==="margin" && <BenefitCostOverview initialItem={seedItem} onOpenProgram={()=>navigate("program")} key={tenant.id+":"+(seedItem?.id||"")}/>}
            {page==="costs" && <CostCatalog tenantId={tenant.id} role={tenant.role} onSimulate={simulateProduct} key={tenant.id}/>}
            {page==="catalog" && <CatalogReconciliation tenantId={tenant.id} role={tenant.role} onOpenSettings={()=>navigate("settings")} key={tenant.id}/>}
            {page==="campaign" && <CampaignGuide tenantId={tenant.id} role={tenant.role} key={tenant.id}/>}
          </>}
        {authError && <div className="portal-auth-error" role="alert">{authError}</div>}
      </main>
    </div>
  </div>;
}
