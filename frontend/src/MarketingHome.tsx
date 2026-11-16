import {ArrowRight, Gift, Heart, ShieldCheck, ShoppingBag, Sparkles, Store, Users} from "lucide-react";
import "./marketing-home.css";

const benefits=[
  {Icon:Users,title:"Clientes mais próximos",description:"Organize uma experiência de clube com regras transparentes e benefícios fáceis de encontrar."},
  {Icon:Gift,title:"Recompensas que encantam",description:"Apresente descontos e vantagens disponíveis, sem esconder condições de participação."},
  {Icon:Heart,title:"Uma relação que continua",description:"Conecte cada visita a um relacionamento duradouro, na loja ou pela internet."}
];

export default function MarketingHome(){
 return <main className="loyalty-home">
  <section className="loyalty-home-hero" aria-labelledby="loyalty-hero-title">
   <div className="loyalty-home-hero-copy">
    <span className="loyalty-home-eyebrow"><Sparkles size={17}/> PROGRAMA DE FIDELIDADE E RECOMPENSAS</span>
    <h1 id="loyalty-hero-title">Seus clientes sempre <em>voltam!</em></h1>
    <p>Transforme compras em relacionamento. Crie um clube para reconhecer seus clientes, apresentar vantagens e incentivar novas visitas.</p>
    <div className="loyalty-home-actions">
     <a className="loyalty-home-button primary" href="/cadastrar">Conhecer o Fideliza <ArrowRight size={19}/></a>
     <a className="loyalty-home-button secondary" href="/conhecer/recursos">Ver benefícios <ArrowRight size={18}/></a>
    </div>
    <div className="loyalty-home-proof" aria-label="Benefícios">
     <span><ShoppingBag size={21}/> Mais motivos para voltar</span>
     <span><Users size={21}/> Clientes mais engajados</span>
     <span><Gift size={21}/> Recompensas com propósito</span>
    </div>
    <p className="loyalty-home-disclaimer"><ShieldCheck size={16}/> Plataforma em homologação: a emissão e o uso de benefícios financeiros dependem de validação.</p>
   </div>
   <div className="loyalty-home-art">
    <div className="loyalty-home-orbit orbit-one"/>
    <div className="loyalty-home-orbit orbit-two"/>
    <img src="/loyalty-gift.svg" alt="Presente roxo com laço dourado, representando as recompensas do clube" className="loyalty-home-gift"/>
    <div className="loyalty-home-sample"><span className="loyalty-home-sample-mark"><Gift size={20}/></span>
     <div><small>EXEMPLO ILUSTRATIVO</small><strong>Seu clube de recompensas</strong><span>Benefícios para a próxima compra</span></div>
    </div>
   </div>
  </section>
  <section className="loyalty-home-benefits" aria-labelledby="loyalty-benefits-title">
   <div className="loyalty-home-section-heading"><span className="loyalty-home-eyebrow">FEITO PARA CRIAR CONEXÕES</span>
    <h2 id="loyalty-benefits-title">Um clube que faz sentido para quem vende e para quem compra.</h2>
    <p>Uma experiência simples, organizada e com os benefícios em destaque.</p>
   </div>
   <div className="loyalty-home-benefit-grid">{benefits.map(({Icon,title,description})=><article key={title}>
    <span className="loyalty-home-benefit-icon"><Icon size={26}/></span><h3>{title}</h3><p>{description}</p>
   </article>)}</div>
  </section>
  <section className="loyalty-home-how">
   <div className="loyalty-home-how-visual"><div className="loyalty-home-how-symbol"><img src="/brand-mark.svg" alt="" width={100} height={100}/></div>
    <span>O relacionamento não termina na compra.</span></div>
   <div className="loyalty-home-how-copy"><span className="loyalty-home-eyebrow">PARA LOJAS FÍSICAS E ONLINE</span>
    <h2>O cliente compra. Seu clube reconhece. A relação continua.</h2>
    <p>Comece pelo programa de pontos e recompensas. Compartilhe seu clube, mostre as condições e acompanhe as participações pelo painel.</p>
    <a href="/conhecer/segmentos">Descubra os segmentos <ArrowRight size={19}/></a>
   </div>
  </section>
  <section className="loyalty-home-cta">
   <div><span>VIDALYS FIDELIZA</span><h2>Pronto para criar um clube com a sua identidade?</h2>
    <p>Conheça o piloto e acompanhe as funcionalidades disponíveis e em validação.</p></div>
   <a href="/cadastrar">Criar minha conta <ArrowRight size={19}/></a>
  </section>
  <div className="loyalty-home-final-note"><Store size={16}/> Fidelidade começa com confiança. Sem promessas de pontos ou descontos antes da ativação.</div>
 </main>;
}
