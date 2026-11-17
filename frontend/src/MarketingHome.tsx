import {ArrowRight, BadgeCheck, BarChart3, Clock3, Gauge, Gift, ShieldCheck, ShoppingBag, Sparkles, Store, Users, Workflow} from "lucide-react";
import "./marketing-home.css";

/* Home comercial. Regras: nada de número de resultado sem fonte, nenhum
   logo de cliente, e todo mockup marcado como exemplo ilustrativo. */

const SOURCE_URL = "https://mundodomarketing.com.br/fidelidade-as-marcas-perde-forca-quando-beneficios-nao-sao-claros-aponta-pesquisa";

const pains = [
  {value: "53,2%", label: "acham as regras claras", copy: "Quem entende o programa recomenda muito mais: NPS 55, contra 20 de quem precisa se esforçar.", answer: "Clube Claro"},
  {value: "19,9%", label: "abandonam por pontos vencidos", copy: "Vencimento é o principal motivo de abandono. 64,7% já perderam benefício por descobrir tarde.", answer: "Pontos sem Susto"},
  {value: "58,4%", label: "entram para chegar a um objetivo", copy: "O cliente quer saber quanto falta para o próximo prêmio, não só quantos pontos tem.", answer: "Meta com Margem"},
];

const steps = [
  {Icon: Sparkles, title: "Monte seu clube", copy: "Defina a regra de pontos, a validade e as recompensas. O Fideliza traduz tudo em frases que o cliente entende."},
  {Icon: Users, title: "Convide seus clientes", copy: "Link do clube, adesão com consentimento e registro de vendas no balcão, com ou sem loja virtual."},
  {Icon: BarChart3, title: "Acompanhe com clareza", copy: "Veja o custo de cada recompensa e a recompra dos clientes, com dados insuficientes indicados como tal."},
];

const channels = [
  {Icon: Store, title: "Loja física", copy: "Registro e conferência de vendas no balcão.", status: "Interface disponível", tone: "ok"},
  {Icon: ShoppingBag, title: "Nuvemshop", copy: "Conexão e leitura de pedidos em teste.", status: "Em homologação", tone: "wait"},
  {Icon: Workflow, title: "WhatsApp", copy: "Convites e avisos pelo Vidalys Flow.", status: "Planejado", tone: "plan"},
];

function PhoneMockup() {
  return <div className="loyalty-home-sample" role="img"
    aria-label="Exemplo ilustrativo do clube no celular: saldo de 420 pontos e meta de recompensa">
    <span className="loyalty-home-sample-tag">EXEMPLO ILUSTRATIVO</span>
    <div className="lh-phone" aria-hidden="true">
      <div className="lh-phone-notch"/>
      <div className="lh-phone-screen">
        <div className="lh-wallet">
          <span className="lh-wallet-store">Clube Ateliê Aurora</span>
          <small>Disponível para trocar</small>
          <strong>420<span> pts</span></strong>
          <em><Clock3 size={12}/> 85 pts a liberar</em>
        </div>
        <div className="lh-expiry"><Clock3 size={14}/><span><b>120 pontos vencem em 6 dias</b>Uma nova compra renova o prazo.</span></div>
        <div className="lh-goal">
          <span className="lh-goal-icon"><Gift size={16}/></span>
          <div><small>Sua próxima meta</small><b>Kit de fitas washi</b></div>
          <div className="lh-progress"><span/></div>
          <p>Faltam 80 pontos, cerca de R$ 80,00 em compras.</p>
        </div>
        <div className="lh-reward"><span className="lh-reward-art"><Gift size={15}/></span>
          <div><b>R$ 20 de desconto</b><small>400 pts</small></div><span className="lh-ok">Pode trocar</span></div>
      </div>
    </div>
    <div className="lh-float lh-float-seal" aria-hidden="true">
      <BadgeCheck size={18}/><div><b>Selo Clube Claro</b><small>Regulamento sem lacunas</small></div>
    </div>
    <div className="lh-float lh-float-margin" aria-hidden="true">
      <Gauge size={18}/><div><b>3,46× de valor</b><small>por real de custo da loja</small></div>
    </div>
    <img src="/loyalty-gift.svg" alt="" className="loyalty-home-gift" width={120} height={120}/>
  </div>;
}

export default function MarketingHome() {
  return <main className="loyalty-home">
    <section className="loyalty-home-hero" aria-labelledby="loyalty-hero-title">
      <div className="loyalty-home-hero-copy">
        <span className="loyalty-home-eyebrow"><Sparkles size={15}/> FIDELIDADE PARA O VAREJO</span>
        <h1 id="loyalty-hero-title">Seus clientes sempre <em>voltam!</em></h1>
        <p className="loyalty-home-lead">O clube que o cliente <strong>entende</strong> e o lojista <strong>consegue pagar</strong>:
          regras claras, pontos sem susto e o custo de cada recompensa à vista.</p>
        <div className="loyalty-home-actions">
          <a className="loyalty-home-button primary" href="/cadastrar">Conhecer o Fideliza <ArrowRight size={18}/></a>
          <a className="loyalty-home-button secondary" href="/demo">Ver demonstração</a>
        </div>
        <ul className="loyalty-home-proof" aria-label="Destaques">
          <li><ShieldCheck size={17}/> Loja física e Nuvemshop</li>
          <li><BadgeCheck size={17}/> Regras em linguagem simples</li>
          <li><Gauge size={17}/> Custo de cada recompensa visível</li>
        </ul>
      </div>
      <div className="loyalty-home-art"><PhoneMockup/></div>
    </section>

    <section className="lh-pains" aria-labelledby="lh-pains-title">
      <div className="lh-heading">
        <span className="loyalty-home-eyebrow">O QUE O CONSUMIDOR DIZ EM 2026</span>
        <h2 id="lh-pains-title">Pontos viraram o básico. O que fideliza é clareza.</h2>
        <p>Dados do Panorama da Fidelização no Brasil 2026 e a resposta do Fideliza para cada um.</p>
      </div>
      <div className="lh-pain-grid">
        {pains.map(item => <article key={item.answer} className="lh-pain">
          <strong className="lh-pain-value">{item.value}</strong>
          <span className="lh-pain-label">{item.label}</span>
          <p>{item.copy}</p>
          <span className="lh-pain-answer"><ArrowRight size={15}/> Nossa resposta: <b>{item.answer}</b></span>
        </article>)}
      </div>
      <p className="lh-source">Fonte: <a href={SOURCE_URL} target="_blank" rel="noopener noreferrer">Panorama da Fidelização no Brasil 2026 (Opinion Box, ABEMF, TSI)</a>, publicado pelo Mundo do Marketing.</p>
    </section>

    <section className="lh-merchant" aria-labelledby="lh-merchant-title">
      <div className="lh-merchant-copy">
        <span className="loyalty-home-eyebrow">PARA QUEM VENDE</span>
        <h2 id="lh-merchant-title">Fidelidade que cabe na margem da loja.</h2>
        <p>Programa de fidelidade costuma ser visto como custo. No Fideliza você enxerga quanto cada
          recompensa custa, quanto os pontos em aberto podem custar e se o clube está de fato trazendo o cliente de volta.</p>
        <ul className="lh-checks">
          <li><BadgeCheck size={18}/> <span><b>Selo Clube Claro:</b> só publica regulamento sem lacunas e com os mesmos prazos do sistema.</span></li>
          <li><Gauge size={18}/> <span><b>Meta com Margem:</b> o cliente é guiado para a recompensa que ele valoriza e que custa pouco para você.</span></li>
          <li><BarChart3 size={18}/> <span><b>Retorno com prova:</b> comparação com grupo de controle e aviso de “dados insuficientes” quando a amostra é pequena.</span></li>
        </ul>
        <a className="lh-text-link" href="/conhecer/recursos">Ver o que já funciona <ArrowRight size={17}/></a>
      </div>
      <div className="lh-board" role="img" aria-label="Exemplo ilustrativo do painel do lojista">
        <span className="lh-board-tag">EXEMPLO ILUSTRATIVO</span>
        <div className="lh-board-head" aria-hidden="true"><BarChart3 size={18}/><b>Saúde do clube</b></div>
        <div className="lh-board-tiles" aria-hidden="true">
          <div><small>Custo potencial dos pontos</small><b>R$ 964 a R$ 2.410</b></div>
          <div><small>Vencem em 30 dias</small><b>2.500 pts</b></div>
          <div><small>Recompra em 90 dias</small><b>34,8%</b><em>entre 27,9% e 42,3%</em></div>
          <div><small>Efeito vs. controle</small><b>Dados insuficientes</b><em>mínimo de 100 por grupo</em></div>
        </div>
        <div className="lh-board-rank" aria-hidden="true">
          <small>Valor para o cliente por R$ 1 de custo</small>
          <div><span>Kit de fitas washi</span><i style={{width: "86%"}}/><b>3,46×</b></div>
          <div><span>Oficina de bordado</span><i style={{width: "100%"}}/><b>4,00×</b></div>
          <div><span>R$ 20 de desconto</span><i style={{width: "25%"}}/><b>1,00×</b></div>
        </div>
      </div>
    </section>

    <section className="lh-steps" aria-labelledby="lh-steps-title">
      <div className="lh-heading">
        <span className="loyalty-home-eyebrow">COMO FUNCIONA</span>
        <h2 id="lh-steps-title">Do cadastro ao cliente voltando, em três passos.</h2>
      </div>
      <ol className="lh-step-list">
        {steps.map(({Icon, title, copy}, index) => <li key={title}>
          <span className="lh-step-number">{index + 1}</span>
          <span className="lh-step-icon"><Icon size={22}/></span>
          <h3>{title}</h3><p>{copy}</p>
        </li>)}
      </ol>
    </section>

    <section className="lh-channels" aria-labelledby="lh-channels-title">
      <div className="lh-heading">
        <span className="loyalty-home-eyebrow">ONDE O CLUBE FUNCIONA</span>
        <h2 id="lh-channels-title">Na loja, no site e, em breve, no WhatsApp.</h2>
        <p>Cada canal com o status real. Sem anunciar integração que ainda não foi testada.</p>
      </div>
      <div className="lh-channel-grid">
        {channels.map(({Icon, title, copy, status, tone}) => <article key={title} className="lh-channel">
          <span className="lh-channel-icon"><Icon size={22}/></span>
          <div><h3>{title}</h3><p>{copy}</p></div>
          <span className={"lh-status lh-status-" + tone}>{status}</span>
        </article>)}
      </div>
      <a className="lh-text-link" href="/conhecer/integracoes">Ver todas as integrações <ArrowRight size={17}/></a>
    </section>

    <section className="loyalty-home-cta">
      <div><span>VIDALYS FIDELIZA</span><h2>Crie o clube da sua loja com regras que o cliente entende.</h2>
        <p>Comece pelo piloto: as funções financeiras são ativadas só depois de validadas.</p></div>
      <a href="/cadastrar">Criar minha conta <ArrowRight size={18}/></a>
    </section>
    <p className="loyalty-home-final-note"><ShieldCheck size={15}/> Fidelidade começa com confiança. Sem promessas de pontos ou descontos antes da ativação.</p>
  </main>;
}
