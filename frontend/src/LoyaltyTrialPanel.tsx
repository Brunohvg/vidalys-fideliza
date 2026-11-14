import {useEffect,useState} from "react";
import {CheckCircle2,Clock3,FlaskConical,Gift,LockKeyhole,ShoppingBag,ShieldAlert} from "lucide-react";
import {ApiError,merchantApi,type DiscountRewardDraft,type PointRuleDraft} from "./api";
import {simulateTrial,type TrialPayment,type TrialStage} from "./loyalty-trial";
import "./loyalty-trial.css";

const toCents=(value:string):number|null=>{
  const match=/^(\d{1,7})(?:[,.](\d{1,2}))?$/.exec(value.trim());
  if(!match)return null;
  const amount=Number(match[1])*100+Number((match[2]||"").padEnd(2,"0"));
  return Number.isSafeInteger(amount)&&amount>=0&&amount<=100_000_000?amount:null;
};
const brl=(amount:number)=>new Intl.NumberFormat("pt-BR",{
  style:"currency",currency:"BRL",
}).format(amount/100);
const whole=(value:number)=>value.toLocaleString("pt-BR");

const messages={
  no_rule:"Salve uma regra de pontos para testar a jornada.",
  no_payment:"Pagamento pendente: nenhum ponto deve entrar na carteira.",
  reversed:"Pedido cancelado ou estornado: nenhum ponto deve ser utilizado.",
  hold:"Os pontos ficam pendentes até terminar a carência.",
  expired:"Pontos vencidos: o cliente não pode usar este saldo.",
  no_reward:"Crie uma recompensa planejada para testar a troca.",
  no_points:"Saldo insuficiente para esta recompensa.",
  order_minimum:"O valor da próxima compra está abaixo do mínimo da recompensa.",
  eligible:"Nesta simulação, a recompensa poderia ser resgatada.",
};

const scenarios:{id:string;label:string;payment:TrialPayment;stage:TrialStage}[]=[
  {id:"pending",label:"Aguardando pagamento",payment:"pending",stage:"waiting"},
  {id:"hold",label:"Em carência",payment:"paid",stage:"waiting"},
  {id:"available",label:"Pontos liberados",payment:"paid",stage:"available"},
  {id:"reversed",label:"Cancelamento",payment:"reversed",stage:"waiting"},
  {id:"expired",label:"Pontos vencidos",payment:"paid",stage:"expired"},
];

export default function LoyaltyTrialPanel({tenantId,ruleRefresh=0,rewardsRefresh=0}:{
  tenantId:string;ruleRefresh?:number;rewardsRefresh?:number;
}){
  const [rule,setRule]=useState<PointRuleDraft|null>(null);
  const [rewards,setRewards]=useState<DiscountRewardDraft[]>([]);
  const [ruleLoading,setRuleLoading]=useState(true);
  const [rewardsLoading,setRewardsLoading]=useState(true);
  const [ruleError,setRuleError]=useState("");
  const [rewardsError,setRewardsError]=useState("");
  const [purchase,setPurchase]=useState("200,00");
  const [checkout,setCheckout]=useState("50,00");
  const [scenario,setScenario]=useState("hold");
  const [rewardId,setRewardId]=useState("");

  useEffect(()=>{
    let active=true;setRule(null);setRuleLoading(true);setRuleError("");
    merchantApi.getPointRuleDraft(tenantId).then(data=>{
      if(active)setRule(data.rule);
    }).catch(error=>{if(active)setRuleError(error instanceof ApiError
      ?error.message:"Não foi possível consultar a regra do clube.");})
      .finally(()=>{if(active)setRuleLoading(false);});
    return()=>{active=false;};
  },[tenantId,ruleRefresh]);
  useEffect(()=>{
    let active=true;setRewards([]);setRewardsLoading(true);setRewardsError("");
    merchantApi.listDiscountRewardDrafts(tenantId).then(data=>{
      if(active)setRewards(data.items);
    }).catch(error=>{if(active)setRewardsError(error instanceof ApiError
      ?error.message:"Não foi possível consultar as recompensas.");})
      .finally(()=>{if(active)setRewardsLoading(false);});
    return()=>{active=false;};
  },[tenantId,rewardsRefresh]);
  useEffect(()=>{
    setPurchase("200,00");setCheckout("50,00");
    setScenario("hold");setRewardId("");
  },[tenantId]);

  const selectedId=rewards.some(x=>x.id===rewardId)?rewardId:(rewards[0]?.id??"");
  const reward=rewards.find(x=>x.id===selectedId)??null;
  const current=scenarios.find(x=>x.id===scenario)??scenarios[1];
  const eligibleCents=toCents(purchase);
  const checkoutCents=toCents(checkout);
  const loading=ruleLoading||rewardsLoading;
  const error=ruleError||rewardsError;
  const result=!loading&&!error&&eligibleCents!==null&&checkoutCents!==null
    ?simulateTrial({eligiblePurchaseCents:eligibleCents,checkoutCents,
       payment:current.payment,stage:current.stage,rule,reward})
    :null;

  return <section className="vf-trial" aria-labelledby="vf-trial-title">
    <header className="vf-trial-heading">
      <span className="vf-trial-icon"><FlaskConical size={21}/></span>
      <div>
        <span className="portal-eyebrow">LABORATÓRIO · SEM ATIVAÇÃO REAL</span>
        <h3 id="vf-trial-title">Teste o caminho dos pontos</h3>
        <p>Simule compras e recompensas usando seus rascunhos. Nada será enviado
          à Nuvemshop, nenhum cliente será afetado e nenhum cupom será criado.</p>
      </div>
    </header>
    {error&&<p className="vf-trial-error" role="alert">{error} Recarregue a página para tentar novamente.</p>}
    <div className="vf-trial-form">
      <div className="vf-trial-scenarios" role="group" aria-label="Situações da compra de teste">
        <strong>Situação da compra</strong>
        <div>
          {scenarios.map(item=><button key={item.id} type="button"
            aria-pressed={scenario===item.id}
            className={scenario===item.id?"selected":""}
            onClick={()=>setScenario(item.id)}>{item.label}</button>)}
        </div>
      </div>
      <div className="vf-trial-inputs">
        <label>Compra elegível de teste (R$)
          <input inputMode="decimal" aria-label="Compra elegível de teste (R$)"
            value={purchase} onChange={event=>setPurchase(event.target.value)}
            placeholder="200,00"/>
        </label>
        <label>Próxima compra no checkout (R$)
          <input inputMode="decimal" aria-label="Próxima compra no checkout (R$)"
            value={checkout} onChange={event=>setCheckout(event.target.value)}
            placeholder="50,00"/>
        </label>
        <label>Recompensa planejada
          <select aria-label="Recompensa planejada" value={selectedId}
            onChange={event=>setRewardId(event.target.value)}
            disabled={rewardsLoading||!rewards.length}>
            {!rewards.length&&<option value="">Nenhuma recompensa salva</option>}
            {rewards.map(item=><option key={item.id} value={item.id}>
              {item.title} · {whole(item.points_cost)} pontos
            </option>)}
          </select>
        </label>
      </div>
      {loading?<p role="status" className="vf-trial-loading">Carregando regras e recompensas…</p>:
        <div className="vf-trial-result" role="region" aria-label="Resultado da simulação">
          <div className="vf-trial-result-grid">
            <div><ShoppingBag size={17}/><span>Pontos gerados pela compra</span>
              <strong>{result?whole(result.earnedPoints):"—"}</strong></div>
            <div><Clock3 size={17}/><span>Pontos pendentes</span>
              <strong>{result?whole(result.pendingPoints):"—"}</strong></div>
            <div><CheckCircle2 size={17}/><span>Pontos disponíveis</span>
              <strong>{result?whole(result.availablePoints):"—"}</strong></div>
            <div><Gift size={17}/><span>Desconto possível no cenário</span>
              <strong>{result?brl(result.discountCents):"—"}</strong></div>
          </div>
          <p className={"vf-trial-outcome "+(result?.eligibleInSimulation?"is-eligible":"")}>
            {result?.eligibleInSimulation?<CheckCircle2 size={19}/>:<ShieldAlert size={19}/>}
            <span>{result?messages[result.reason]:"Preencha valores válidos para simular."}</span>
          </p>
          {result?.eligibleInSimulation&&<p className="vf-trial-note">
            Pontos necessários: {whole(result.redeemedPoints)}. Saldo teórico após a
            troca: {whole(result.remainingPoints)} pontos. A simulação não reserva nem
            consome pontos de nenhuma carteira.
          </p>}
          <p className="vf-trial-warning"><LockKeyhole size={16}/>
            Cenário hipotético de um pedido, sem prova de pagamento, cálculo de
            frete/margem ou confirmação de uso do cupom. Carência e validade
            são representadas por estados de teste, não pelo relógio real.</p>
        </div>}
    </div>
  </section>;
}
