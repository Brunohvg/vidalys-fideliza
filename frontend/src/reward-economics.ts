/** Prévia de economia do clube: sem emissão de pontos e sem inferir lucro. */
export type RuleForEstimate = {points:number;per_cents:number};

export type RewardEstimate = {
  /** Valor elegível acumulado necessário partindo de saldo zero, em centavos. */
  eligibleSpendCents:number|null;
  /** Desconto nominal máximo para o limite configurado, em centavos. */
  nominalExposureCents:number;
  /** Percentual equivalente ao gasto elegível para obter a recompensa. */
  benefitRateBps:number|null;
};

/** O motor usa floor(valor*points/per_cents). A inversão exata usa ceil. */
export function estimateReward(
  pointsCost:number, discountCents:number, maxRedemptions:number,
  rule:RuleForEstimate|null,
):RewardEstimate|null {
  const valid=(v:number,max:number)=>Number.isSafeInteger(v)&&v>0&&v<=max;
  if(!valid(pointsCost,1_000_000)||!valid(discountCents,1_000_000)
     ||!valid(maxRedemptions,100_000))return null;
  const nominalExposureCents=discountCents*maxRedemptions;
  if(!Number.isSafeInteger(nominalExposureCents))return null;
  if(!rule||!valid(rule.points,100_000)||!valid(rule.per_cents,100_000_000)){
    return {eligibleSpendCents:null,nominalExposureCents,benefitRateBps:null};
  }
  const spend=Math.ceil(pointsCost*rule.per_cents/rule.points);
  if(!Number.isSafeInteger(spend)||spend<=0||spend>100_000_000){
    return {eligibleSpendCents:null,nominalExposureCents,benefitRateBps:null};
  }
  const bps=Math.round(discountCents*10000/spend);
  return {eligibleSpendCents:spend,nominalExposureCents,
          benefitRateBps:Number.isSafeInteger(bps)?bps:null};
}
