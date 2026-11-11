import { useState } from "react";
import MarginSimulator from "./MarginSimulator";
import {
  ArrowRight, ArrowUpRight, BarChart3, Check, ChevronDown,
  CircleHelp, Gift, LayoutDashboard, Menu, Plus, Settings2,
  ShieldCheck, TrendingUp, Users, Wallet, X, Calculator
} from "lucide-react";

const nav = [
  { key: "overview", text: "Visão geral", icon: LayoutDashboard },
  { key: "programs", text: "Programas", icon: Gift },
  { key: "wallets", text: "Carteiras", icon: Wallet },
  { key: "margin", text: "Rentabilidade", icon: Calculator },
  { key: "insights", text: "Resultados", icon: BarChart3 }
] as const;

type Page = (typeof nav)[number]["key"];
function Brand() {
  return <div className="brand" aria-label="Vidalys Fideliza">
    <div className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 44 44" fill="none" width="44" height="44">
        <rect x="1" y="1" width="42" height="42" rx="13" fill="#087F79" />
        <path d="m11 13 11 20 11-20" stroke="#fff" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M13 30c8 7 19 4 23-8" stroke="#37D5BB" strokeWidth="2.7" strokeLinecap="round" />
      </svg>
    </div>
    <span className="brand-copy">vidalys<span>fideliza</span></span>
  </div>;
}

function StatCard({ title, amount, foot, icon: Icon, variant }: {
  title: string; amount: string; foot: string; icon: typeof Gift; variant: string;
}) {
  return <article className="stat-card">
    <div className="stat-top"><span>{title}</span><span className={"stat-icon " + variant}><Icon size={19} /></span></div>
    <strong>{amount}</strong>
    <div className="stat-foot"><TrendingUp size={14} /> {foot}</div>
  </article>;
}

const months = [
  { month: "Mai", count: 37 }, { month: "Jun", count: 49 }, { month: "Jul", count: 42 },
  { month: "Ago", count: 63 }, { month: "Set", count: 58 }, { month: "Out", count: 83 }
];

const rows = [
  { initials: "MC", name: "Mariana Costa", kind: "Crédito liberado", time: "Hoje, 10h42", amount: "+ R$ 8,40", tone: "green" },
  { initials: "RA", name: "Rafael Alves", kind: "Recompensa resgatada", time: "Ontem, 16h20", amount: "− R$ 5,00", tone: "blue" },
  { initials: "CL", name: "Carla Lima", kind: "Crédito pendente", time: "Ontem, 14h06", amount: "+ R$ 4,60", tone: "amber" }
];

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [drawer, setDrawer] = useState(false);
  const [info, setInfo] = useState(false);
  const title = nav.find(p => p.key === page)?.text || "Visão geral";
  const navigate = (next: Page) => { setPage(next); setDrawer(false); };

  return <div className="layout">
    <aside className={"sidebar" + (drawer ? " open" : "")} aria-label="Menu do aplicativo">
      <div className="sidebar-head"><Brand/><button className="close-mobile" aria-label="Fechar menu" onClick={() => setDrawer(false)}><X size={21}/></button></div>
      <div className="shop-select"><span className="shop-avatar">V</span><span className="shop-copy"><b>Loja demonstração</b><small>Ambiente de protótipo</small></span><ChevronDown size={15}/></div>
      <span className="nav-heading">ESPAÇO DE TRABALHO</span>
      <nav className="nav" aria-label="Seções">
        {nav.map(item => {
          const Icon = item.icon;
          return <button key={item.key} className={"nav-link" + (page === item.key ? " selected" : "")}
            aria-current={page === item.key ? "page" : undefined} onClick={() => navigate(item.key)}>
            <Icon size={19}/><span>{item.text}</span>
          </button>;
        })}
      </nav>
      <span className="nav-heading settings-heading">FERRAMENTAS</span>
      <button className="nav-link" onClick={() => navigate("margin")}><Settings2 size={19}/>Simular rentabilidade</button>
      <button className="nav-link" onClick={() => setInfo(true)}><CircleHelp size={19}/>Sobre o protótipo</button>
      <div className="sidebar-bottom">
        <div className="sidebar-tip"><span className="tip-symbol"><ShieldCheck size={20}/></span><b>Incentivos com inteligência.</b><p>Recompensa boa é aquela que cabe na margem da loja.</p><button onClick={() => navigate("margin")}>Fazer simulação <ArrowRight size={16}/></button></div>
        <small className="sidebar-version">FIDELIZA <span>•</span> VISUAL P0</small>
      </div>
    </aside>
    {drawer && <button aria-label="Fechar navegação" className="overlay" onClick={() => setDrawer(false)} />}
    <main className="main">
      <header className="topbar">
        <div className="topbar-left"><button className="open-mobile" aria-label="Abrir menu" onClick={() => setDrawer(true)}><Menu size={22}/></button><span>Plataforma</span><span className="slash">/</span><b>{title}</b></div>
        <div className="topbar-right"><span className="sample-pill"><span/> DADOS FICTÍCIOS</span><button className="profile" title="Informações do protótipo" onClick={() => setInfo(true)}>VF</button></div>
      </header>
      <div className="content">
        <div className="intro">
          <div className="intro-copy"><div className="eyebrow">VIDALYS FIDELIZA <span>•</span> CONCEITO VISUAL</div><h1>{page === "overview" ? "Sua fidelidade, em movimento." : title}</h1>
            <p>{page === "overview" ? "Transforme cada compra em um motivo para voltar. Com controle, clareza e uma experiência que seu cliente merece." : "Uma operação de recompensas transparente, preparada para crescer com a sua loja."}</p></div>
          {page !== "margin" && <button className="button-primary" onClick={() => page === "overview" ? navigate("programs") : navigate("margin")}><Plus size={18}/>{page === "overview" ? "Explorar programas" : "Simular rentabilidade"}</button>}
        </div>

        {page === "overview" && <>
          <div className="stats" aria-label="Números de demonstração">
            <StatCard title="Créditos emitidos" amount="R$ 3.284,90" foot="Exemplo ilustrativo" icon={Wallet} variant="blue"/>
            <StatCard title="Clientes participantes" amount="284" foot="Exemplo ilustrativo" icon={Users} variant="cyan"/>
            <StatCard title="Recompensas usadas" amount="97" foot="Exemplo ilustrativo" icon={Gift} variant="violet"/>
            <StatCard title="Taxa de recompra" amount="28,6%" foot="Exemplo ilustrativo" icon={TrendingUp} variant="green"/>
          </div>
          <div className="dashboard-grid">
            <section className="panel chart-panel"><div className="panel-header"><div><span className="panel-kicker">RETENÇÃO</span><h2>Clientes voltando a comprar</h2><p>Evolução ilustrativa de recompra</p></div><span className="soft-label">6 meses</span></div>
              <div className="chart" role="img" aria-label="Dados fictícios de evolução mensal de recompra: maio 37, junho 49, julho 42, agosto 63, setembro 58, outubro 83">
                {months.map(m => <div className="bar-wrap" key={m.month}><div className="bar-track"><div className="bar" style={{ height: String(m.count) + "%" }}/></div><span>{m.month}</span></div>)}
              </div>
            </section>
            <section className="panel card-feature"><span className="feature-icon"><Gift size={25}/></span><span className="feature-eyebrow">SEU PROGRAMA</span><h2>Fidelize com mais controle</h2><p>Crie programas de pontos ou cashback com regras claras, limites e histórico auditável.</p><div className="feature-divider"/><div className="feature-row"><Check size={16}/> Créditos com validade definida</div><div className="feature-row"><Check size={16}/> Resgates controlados</div><div className="feature-row"><Check size={16}/> Foco em margem e recompra</div><button className="feature-button" onClick={() => navigate("programs")}>Explorar estrutura <ArrowUpRight size={16}/></button></section>
          </div>
          <section className="panel activity"><div className="panel-header"><div><span className="panel-kicker">ATIVIDADE</span><h2>Movimentações recentes</h2></div><span className="soft-label">Exemplo</span></div>
            <div className="activity-list">{rows.map(r => <div className="activity-row" key={r.name}><span className="person-avatar">{r.initials}</span><div className="person-info"><b>{r.name}</b><span>{r.kind} · {r.time}</span></div><strong className={r.tone}>{r.amount}</strong></div>)}</div>
          </section>
        </>}

        {page === "programs" && <div className="secondary-grid">
          <section className="panel program-panel"><span className="panel-kicker">MODALIDADE 01</span><div className="program-icon blue"><Wallet size={25}/></div><h2>Cashback promocional</h2><p>Uma porcentagem da compra vira crédito para a próxima compra. Sem transferência ou saque.</p><div className="program-bottom"><span className="soft-label">Planejado para o MVP</span><button onClick={() => navigate("margin")}>Simular <ArrowRight size={17}/></button></div></section>
          <section className="panel program-panel"><span className="panel-kicker">MODALIDADE 02</span><div className="program-icon cyan"><Gift size={25}/></div><h2>Pontos de fidelidade</h2><p>Pontos acumulados por compras elegíveis, convertidos em descontos futuros.</p><div className="program-bottom"><span className="soft-label">Planejado para o MVP</span><button onClick={() => setInfo(true)}>Entenda <ArrowRight size={17}/></button></div></section>
        </div>}

        {page === "wallets" && <div className="wallets-layout">
          <section className="wallet-demo"><span className="wallet-brand">EXEMPLO DA CARTEIRA DO COMPRADOR</span><span className="wallet-caption">Crédito disponível</span><strong>R$ 27,50</strong><span className="wallet-status"><Check size={15}/> Saldo demonstrativo</span><div className="wallet-divider"/><div className="wallet-split"><span>Crédito pendente<b>R$ 8,40</b></span><span>Vencimento mais próximo<b>20/12/2026</b></span></div></section>
          <section className="panel guide"><span className="panel-kicker">EXPERIÊNCIA DO CLIENTE</span><h2>O benefício é simples. A regra é transparente.</h2><p>O comprador poderá consultar seus créditos, entender quando serão liberados e resgatar conforme as regras da loja.</p><div className="guide-note"><ShieldCheck size={18}/> Os dados exibidos aqui são fictícios; nenhuma carteira real foi criada.</div></section>
        </div>}

        {page === "margin" && <MarginSimulator />}

        {page === "insights" && <section className="panel insights"><span className="panel-kicker">INTELIGÊNCIA COMERCIAL</span><h2>Mais do que distribuir descontos.</h2><p>O Vidalys Fideliza acompanhará recorrência, custo dos benefícios e impacto comercial. Nesta versão, os indicadores ainda são demonstrativos.</p><div className="insight-tags"><span>Segunda compra</span><span>Margem após incentivo</span><span>Créditos pendentes</span><span>Retenção por período</span></div><button className="button-primary" onClick={() => navigate("margin")}>Testar simulação <ArrowRight size={17}/></button></section>}
        <div className="prototype-footer"><ShieldCheck size={15}/> Ambiente demonstrativo. Nenhum dado ou operação de loja conectado.</div>
      </div>
    </main>
    {info && <div className="dialog-scrim" role="presentation" onClick={() => setInfo(false)}><div className="dialog" role="dialog" aria-modal="true" aria-labelledby="info-title" onClick={e => e.stopPropagation()}><div className="dialog-head"><span className="panel-kicker">SOBRE</span><button aria-label="Fechar informações" onClick={() => setInfo(false)}><X size={20}/></button></div><h2 id="info-title">Um conceito visual, não um programa ativo.</h2><p>Esta interface demonstra a identidade Vidalys. Não existe integração OAuth, geração de cashback nem carteira conectada. A estrutura Django está sendo desenvolvida separadamente.</p><button className="button-primary close-info" onClick={() => setInfo(false)}>Entendi <Check size={16}/></button></div></div>}
  </div>;
}
