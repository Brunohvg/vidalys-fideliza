import MarketingHome from "./MarketingHome";
import {useEffect,useMemo,useState} from "react";
import {
  ArrowRight, Coffee,
  Gift, HeartHandshake, Mail, Paintbrush, PawPrint, Scissors, Search,
  ShieldCheck, ShoppingBag, Sparkles, Store, TicketPercent, Workflow
} from "lucide-react";
import "./marketing.css";

type Page="inicio"|"recursos"|"segmentos"|"integracoes";
type CapabilityStatus="interface"|"homologacao"|"planejado";
const nav:{page:Page;label:string;href:string}[]=[
  {page:"inicio",label:"Início",href:"/"},
  {page:"recursos",label:"Recursos",href:"/conhecer/recursos"},
  {page:"segmentos",label:"Segmentos",href:"/conhecer/segmentos"},
  {page:"integracoes",label:"Integrações",href:"/conhecer/integracoes"},
];
const statuses:Record<CapabilityStatus,{label:string;description:string}>={
  interface:{label:"Interface disponível",description:"Código disponível; requer validar o ambiente publicado"},
  homologacao:{label:"Em homologação",description:"Integração ou operação financeira ainda não validada integralmente"},
  planejado:{label:"Planejado",description:"Ainda não é uma integração ou função disponível"},
};
const features=[
  {title:"Clube com a marca da sua loja",description:"Uma página de adesão com regulamento, consentimento e acesso independente por e-mail.",status:"interface" as CapabilityStatus,Icon:HeartHandshake},
  {title:"Recompensas em destaque",description:"O cliente vê os benefícios publicados e as condições, antes de qualquer resgate.",status:"interface" as CapabilityStatus,Icon:Gift},
  {title:"Vendas de balcão",description:"Registro e conferência de vendas presenciais. Ainda não vale como liquidação financeira.",status:"interface" as CapabilityStatus,Icon:Store},
  {title:"Compras da Nuvemshop",description:"Conector, leitura de pedidos e eventos desenvolvidos para teste em loja autorizada.",status:"homologacao" as CapabilityStatus,Icon:ShoppingBag},
  {title:"Pontos e descontos resgatáveis",description:"O motor existe, mas depende de pagamento comprovado, titularidade e checkout seguro.",status:"homologacao" as CapabilityStatus,Icon:TicketPercent},
  {title:"Mensagens de recompra",description:"Campanhas por e-mail e WhatsApp podem integrar uma evolução futura, depois do piloto.",status:"planejado" as CapabilityStatus,Icon:Mail},
];
const segments=[
  {title:"Moda e acessórios",Icon:ShoppingBag,copy:"Transforme clientes ocasionais em pessoas que acompanham sua próxima coleção.",example:"Exemplo de programa: pontos em compras elegíveis e desconto na próxima visita."},
  {title:"Artesanato e aviamentos",Icon:Paintbrush,copy:"Incentive novas compras de quem repõe materiais para criar, costurar e produzir.",example:"Exemplo de programa: recompensa em compras recorrentes de materiais."},
  {title:"Cafés e pequenos restaurantes",Icon:Coffee,copy:"Crie um motivo a mais para o cliente voltar ao seu estabelecimento.",example:"Exemplo de programa: prêmio por compras verificadas, após configuração."},
  {title:"Petshops",Icon:PawPrint,copy:"Acompanhe o relacionamento com quem compra produtos e serviços para seus animais.",example:"Exemplo de programa: pontos em compras recorrentes de produtos."},
  {title:"Salões e barbearias",Icon:Scissors,copy:"Reforce o vínculo com quem retorna para um novo serviço.",example:"Exemplo de programa: benefícios em visitas elegíveis."},
  {title:"Varejo local",Icon:Store,copy:"Comece com um clube simples, mesmo sem site ou equipe técnica.",example:"Exemplo de programa: adesão por link e conferência de venda presencial."},
];
const integrations=[
  {title:"Nuvemshop",category:"E-commerce",status:"homologacao" as CapabilityStatus,copy:"OAuth, consulta de pedidos e conciliação em teste. Resgate comercial ainda bloqueado."},
  {title:"Venda presencial",category:"Operação própria",status:"interface" as CapabilityStatus,copy:"Registro manual e vínculo ao participante; comprovação de pagamento é uma etapa separada."},
  {title:"Vidalys Flow",category:"WhatsApp",status:"planejado" as CapabilityStatus,copy:"Conector futuro para vendas pelo WhatsApp, sem ligação automática hoje."},
  {title:"Outros ERPs e plataformas",category:"Futuras conexões",status:"planejado" as CapabilityStatus,copy:"Integrações futuras serão anunciadas individualmente após desenvolvimento e testes."},
];
function currentPage():Page {
  const path=window.location.pathname.replace(/\/+$/,"")||"/";
  const match=nav.find(item=>item.href===path);
  return match?.page||"inicio";
}
function Status({value}:{value:CapabilityStatus}){
  return <span className={"mk-state mk-state-"+value} title={statuses[value].description}>{statuses[value].label}</span>;
}
function SectionTop({eyebrow,title,copy}:{eyebrow:string;title:string;copy:string}){
  return <div className="mk-section-top">
    <span className="mk-eyebrow"><Sparkles size={15}/>{eyebrow}</span>
    <h1>{title}</h1><p>{copy}</p>
  </div>;
}
export default function MarketingSite(){
  const page=currentPage();
  const [category,setCategory]=useState("Todas");
  const [search,setSearch]=useState("");
  const filtered=useMemo(()=>integrations.filter(item=>
    (category==="Todas"||item.category===category)
      &&(item.title+" "+item.copy+" "+item.category).toLocaleLowerCase("pt-BR")
        .includes(search.toLocaleLowerCase("pt-BR").trim())
  ),[category,search]);
  useEffect(()=>{
    const label=nav.find(item=>item.page===page)?.label||"Início";
    document.title="Vidalys Fideliza · "+label+" · Prévia comercial";
  },[page]);
  return <div className="vf-market">
    <header className="mk-header">
      <div className="mk-header-inner">
        <a className="mk-logo" href="/" aria-label="Vidalys Fideliza · início">
          <img src="/brand-logo.svg" alt="Vidalys Fideliza" width={175} height={51} />
        </a>
        <nav className="mk-nav" aria-label="Apresentação comercial">
          {nav.map(item=><a key={item.page} href={item.href}
            aria-current={page===item.page?"page":undefined}>{item.label}</a>)}
        </nav>
        <div className="mk-header-actions">
          <a className="mk-signin" href="/entrar">Entrar</a>
          <a className="mk-head-cta" href="/cadastrar">Criar conta <ArrowRight size={16}/></a>
        </div>
      </div>
    </header>
    {page==="inicio"&&<MarketingHome/>}
    {page==="recursos"&&<main className="mk-inner">
      <SectionTop eyebrow="RECURSOS" title="O que você pode fazer com o Fideliza."
        copy="Uma visão clara das funcionalidades do produto, separando as interfaces existentes das integrações que ainda exigem homologação."/>
      <div className="mk-feature-grid">
        {features.map(item=>{const Icon=item.Icon;return <article className="mk-feature" key={item.title}>
          <div className="mk-feature-symbol"><Icon size={25}/></div>
          <Status value={item.status}/><h2>{item.title}</h2><p>{item.description}</p>
        </article>})}
      </div>
      <div className="mk-disclosure"><ShieldCheck size={22}/><p><strong>Sem promessas antecipadas.</strong> Uma interface disponível não significa que pagamento, crédito ou resgate comercial já esteja habilitado. O piloto exige validação própria.</p></div>
    </main>}
    {page==="segmentos"&&<main className="mk-inner">
      <SectionTop eyebrow="SEGMENTOS" title="Uma ideia de fidelidade para cada negócio."
        copy="O melhor programa combina com a rotina da sua loja. Explore exemplos de uso, não regras que já estejam automaticamente ativadas."/>
      <div className="mk-segments">
        {segments.map(item=>{const Icon=item.Icon;return <article className="mk-segment" key={item.title}>
          <span className="mk-segment-icon"><Icon size={26}/></span>
          <h2>{item.title}</h2><p>{item.copy}</p>
          <div className="mk-segment-example"><Gift size={19}/><span>{item.example}</span></div>
          <a className="mk-text-link" href="/conhecer/recursos">Como funciona <ArrowRight size={17}/></a>
        </article>})}
      </div>
      <p className="mk-disclaimer">Os cenários acima são sugestões editoriais de utilização. A operação de pontos e resgates depende de integração financeira validada.</p>
    </main>}
    {page==="integracoes"&&<main className="mk-inner">
      <SectionTop eyebrow="INTEGRAÇÕES" title="Seu negócio não precisa trocar de sistema para começar."
        copy="Comece com seu clube e conheça os canais suportados pelo projeto. O status de cada conexão é apresentado sem exageros."/>
      <div className="mk-integration-intro">
        <div><span><Store size={26}/></span><h2>Sem loja virtual? Tudo bem.</h2><p>O painel oferece registro e conferência de vendas presenciais, sem exigir uma Nuvemshop.</p></div>
        <div><span><Workflow size={26}/></span><h2>Tem e-commerce?</h2><p>A integração Nuvemshop está em homologação. Pagamento, pontuação e resgate ainda precisam de testes externos.</p></div>
      </div>
      <div className="mk-filter">
        <label><Search size={19}/><span className="mk-visually-hidden">Buscar integração</span>
          <input type="search" value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="Buscar integração ou canal…"/></label>
        <label className="mk-category">Categoria
          <select value={category} onChange={e=>setCategory(e.target.value)}>
            <option>Todas</option>{[...new Set(integrations.map(i=>i.category))].map(c=><option key={c}>{c}</option>)}
          </select>
        </label>
      </div>
      <div className="mk-integration-grid">
        {filtered.map(item=><article key={item.title} className="mk-integration">
          <span className="mk-category-label">{item.category}</span>
          <h2>{item.title}</h2><p>{item.copy}</p><Status value={item.status}/>
        </article>)}
      </div>
      {filtered.length===0&&<div className="mk-empty" role="status">Nenhuma integração encontrada com esses filtros.</div>}
      <p className="mk-disclaimer">Não anunciamos integração com ERPs, marketplaces ou CRMs sem contrato técnico e testes de ponta a ponta.</p>
    </main>}
    <footer className="mk-footer"><div className="mk-footer-inner">
      <div><div className="mk-footer-brand"><img src="/brand-logo-white.svg" alt="Vidalys Fideliza" width={180} height={52}/></div>
        <p>Relacionamento, recompensas e cuidado com cada compra.</p>
        <small>Esta apresentação é uma prévia de homologação, não uma oferta de recursos comerciais ativados.</small>
      </div>
      <nav aria-label="Links do rodapé">{nav.map(item=><a key={item.page} href={item.href}>{item.label}</a>)}<a href="/entrar">Entrar</a></nav>
    </div></footer>
  </div>;
}
