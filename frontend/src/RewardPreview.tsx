import {Gift, LockKeyhole, Sparkles, Wallet} from "lucide-react";
import {brl} from "./finance";

type RewardPreviewProps = {
  creditCents: number;
  goal: string;
};

/** Apenas apresentação. Não consulta saldo nem permite resgate. */
export default function RewardPreview({creditCents,goal}:RewardPreviewProps){
  return <aside className="vf-reward-preview" aria-label="Prévia ilustrativa da recompensa">
    <div className="vf-reward-preview-copy">
      <span className="vf-preview-kicker"><Sparkles size={16}/> EXPERIÊNCIA DO COMPRADOR</span>
      <h3>O benefício precisa<br/>ser fácil de entender.</h3>
      <p>Assim o comprador poderá visualizar uma recompensa. O cartão abaixo é uma <strong>simulação visual</strong>, não uma carteira habilitada.</p>
      <div className="vf-preview-note"><LockKeyhole size={17}/>
        <span>Saldo, prazo, elegibilidade e resgate ainda dependem da implementação e validação com a loja.</span>
      </div>
    </div>
    <div className="vf-phone-frame" aria-label="Exemplo de tela no celular">
      <div className="vf-phone-top"><span>fideliza</span><span className="vf-phone-dot"/></div>
      <div className="vf-wallet-card">
        <div className="vf-wallet-top"><span><Wallet size={16}/> SUA RECOMPENSA</span><Gift size={17}/></div>
        <span className="vf-wallet-small">Exemplo de crédito por compra</span>
        <strong>{brl(creditCents)}</strong>
        <div className="vf-wallet-divider"/>
        <span className="vf-wallet-goal">Objetivo: {goal}</span>
      </div>
      <div className="vf-wallet-future"><LockKeyhole size={15}/>
        <span>Exemplo demonstrativo · Não disponível para uso</span>
      </div>
    </div>
  </aside>;
}
