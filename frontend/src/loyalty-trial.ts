/** Laboratório de fidelidade: cálculo local, NUNCA grava crédito/cupom.
 * Valores monetários em centavos, pontos inteiros, no máximo uma compra base.
 */
export type TrialPayment="paid"|"pending"|"reversed";
export type TrialStage="waiting"|"available"|"expired";
export type TrialRule={
  points:number;per_cents:number;hold_days:number;validity_days:number;
};
export type TrialReward={
  points_cost:number;discount_cents:number;min_order_cents:number;
};
export type TrialResult={
  earnedPoints:number;pendingPoints:number;availablePoints:number;
  redeemedPoints:number;remainingPoints:number;discountCents:number;
  eligibleInSimulation:boolean;
  reason:"no_payment"|"reversed"|"hold"|"expired"|"no_rule"|
    "no_reward"|"no_points"|"order_minimum"|"eligible";
};

const whole=(value:number,max:number)=>Number.isSafeInteger(value)&&value>=0&&value<=max;

/** Uma compra: mesma regra de floor por pedido usada na prévia existente. */
export function simulateTrial(input:{
  eligiblePurchaseCents:number;checkoutCents:number;
  payment:TrialPayment;stage:TrialStage;
  rule:TrialRule|null;reward:TrialReward|null;
}):TrialResult|null {
  const {eligiblePurchaseCents,checkoutCents,payment,stage,rule,reward}=input;
  if(!whole(eligiblePurchaseCents,100_000_000)||
     !whole(checkoutCents,100_000_000)||
     !["paid","pending","reversed"].includes(payment)||
     !["waiting","available","expired"].includes(stage))return null;
  const validRule=!!rule&&whole(rule.points,100_000)&&rule.points>0&&
    whole(rule.per_cents,100_000_000)&&rule.per_cents>=100&&
    whole(rule.hold_days,90)&&whole(rule.validity_days,1095)&&rule.validity_days>=1;
  const validReward=!!reward&&whole(reward.points_cost,1_000_000)&&reward.points_cost>0&&
    whole(reward.discount_cents,1_000_000)&&reward.discount_cents>=100&&
    whole(reward.min_order_cents,100_000_000)&&
    reward.min_order_cents>=reward.discount_cents;
  const earned=validRule?Math.floor(eligiblePurchaseCents*rule!.points/rule!.per_cents):0;
  if(!whole(earned,100_000_000))return null;
  const paid=payment==="paid";
  const pending=paid&&stage==="waiting"?earned:0;
  const available=paid&&stage==="available"?earned:0;
  let reason:TrialResult["reason"]="eligible";
  if(!validRule)reason="no_rule";
  else if(payment==="pending")reason="no_payment";
  else if(payment==="reversed")reason="reversed";
  else if(stage==="waiting")reason="hold";
  else if(stage==="expired")reason="expired";
  else if(!validReward)reason="no_reward";
  else if(available<reward!.points_cost)reason="no_points";
  else if(checkoutCents<reward!.min_order_cents)reason="order_minimum";
  const can=reason==="eligible";
  const redeemed=can?reward!.points_cost:0;
  return {
    earnedPoints:paid?earned:0,
    pendingPoints:pending,
    availablePoints:available,
    redeemedPoints:redeemed,
    remainingPoints:available-redeemed,
    discountCents:can?reward!.discount_cents:0,
    eligibleInSimulation:can,
    reason,
  };
}
