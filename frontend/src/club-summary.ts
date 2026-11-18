/* "Seu clube em uma frase": junta regra e recompensas e devolve o que o lojista
   precisa saber sem fazer conta. Função pura; nada aqui concede pontos.

   Ponto com preço: cada recompensa de desconto dá ao ponto um valor implícito
   (desconto ÷ pontos). Se as recompensas discordam, o cliente percebe valores
   diferentes para o mesmo ponto; o resumo avisa em vez de esconder. */
import {estimateReward} from "./reward-economics";

export type SummaryRule={points:number;per_cents:number;hold_days:number;validity_days:number};
export type SummaryReward={title:string;points_cost:number;discount_cents:number;published:boolean};

export type ClubStage="setup"|"ready";
export type SummaryWarning={key:"no_rule"|"no_reward"|"inconsistent_value"|"high_rate"|"unreachable";text:string};

export type ClubSummary={
  stage:ClubStage;
  sentences:string[];
  /** Porcentagem devolvida ao cliente na recompensa mais vantajosa, em pontos-base. */
  returnBps:{min:number;max:number}|null;
  /** Valor implícito de 1 ponto, em centésimos de centavo (para precisão). */
  pointValue:{min:number;max:number}|null;
  warnings:SummaryWarning[];
};

const brl=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const pts=(value:number)=>`${value.toLocaleString("pt-BR")} ponto${value===1?"":"s"}`;
const days=(value:number)=>`${value} dia${value===1?"":"s"}`;
export const percentText=(bps:number)=>
  `${(bps/100).toLocaleString("pt-BR",{maximumFractionDigits:bps%100===0?0:1})}%`;
/** Valor de 1 ponto em reais, com até 4 casas quando for menor que um centavo. */
export const pointValueText=(hundredthCents:number)=>
  (hundredthCents/10000).toLocaleString("pt-BR",{style:"currency",currency:"BRL",
    minimumFractionDigits:2,maximumFractionDigits:hundredthCents%100===0?2:4});

const HIGH_RATE_BPS=1000;          // acima de 10% devolvido merece revisão
const INCONSISTENT_SPREAD=1.25;    // recompensas que divergem mais de 25%

export function summarizeClub(rule:SummaryRule|null,rewards:SummaryReward[]):ClubSummary{
  const warnings:SummaryWarning[]=[];
  const sentences:string[]=[];
  const pool=rewards.some(item=>item.published)?rewards.filter(item=>item.published):rewards;

  if(rule){
    sentences.push(`A cada ${brl(rule.per_cents)} em compras, o cliente ganha ${pts(rule.points)}.`);
    sentences.push(rule.hold_days===0
      ?`Os pontos ficam disponíveis logo após a compra paga e valem por ${days(rule.validity_days)}.`
      :`Os pontos ficam disponíveis ${days(rule.hold_days)} depois da compra paga e valem por ${days(rule.validity_days)}.`);
  }else{
    warnings.push({key:"no_rule",text:"Defina como o cliente ganha pontos para calcular quanto ele recebe de volta."});
  }

  if(pool.length===0){
    warnings.push({key:"no_reward",text:"Crie a primeira recompensa: sem ela, os pontos não têm valor para o cliente."});
  }

  const values=pool.map(item=>Math.round(item.discount_cents*100/item.points_cost))
    .filter(value=>Number.isSafeInteger(value)&&value>0);
  const pointValue=values.length?{min:Math.min(...values),max:Math.max(...values)}:null;

  const rates=rule?pool.map(item=>estimateReward(item.points_cost,item.discount_cents,1,rule)?.benefitRateBps)
    .filter((value):value is number=>typeof value==="number"):[];
  const returnBps=rates.length?{min:Math.min(...rates),max:Math.max(...rates)}:null;

  if(rule&&pool.length){
    const cheapest=[...pool].sort((a,b)=>a.points_cost-b.points_cost)[0];
    const spend=estimateReward(cheapest.points_cost,cheapest.discount_cents,1,rule)?.eligibleSpendCents;
    sentences.push(`${pts(cheapest.points_cost)} viram ${brl(cheapest.discount_cents)} de desconto`
      +(spend?` (cerca de ${brl(spend)} em compras).`:"."));
    if(spend===null||spend===undefined)
      warnings.push({key:"unreachable",text:`“${cheapest.title}” exige mais compras do que o sistema consegue calcular. Revise os pontos.`});
  }
  if(returnBps){
    sentences.push(returnBps.min===returnBps.max
      ?`Na prática, o cliente recebe ${percentText(returnBps.max)} de volta.`
      :`Na prática, o cliente recebe de ${percentText(returnBps.min)} a ${percentText(returnBps.max)} de volta, conforme a recompensa.`);
    if(returnBps.max>HIGH_RATE_BPS)
      warnings.push({key:"high_rate",text:`Uma recompensa devolve ${percentText(returnBps.max)} das compras. Confira se a margem comporta.`});
  }
  if(pointValue&&pointValue.max>pointValue.min*INCONSISTENT_SPREAD){
    warnings.push({key:"inconsistent_value",
      text:`Suas recompensas dão valores diferentes ao ponto (de ${pointValueText(pointValue.min)} a ${pointValueText(pointValue.max)}). `
        +"O ideal é um preço só, para o cliente entender quanto vale o saldo."});
  }
  const ready=Boolean(rule)&&pool.some(item=>item.published)&&!warnings.some(w=>w.key==="unreachable");
  return {stage:ready?"ready":"setup",sentences,returnBps,pointValue,warnings};
}
