import {describe,expect,it} from "vitest";
import {simulateTrial,type TrialPayment,type TrialStage} from "./loyalty-trial";

const base={
  eligiblePurchaseCents:20000,checkoutCents:5000,
  payment:"paid" as TrialPayment,stage:"available" as TrialStage,
  rule:{points:1,per_cents:100,hold_days:7,validity_days:180},
  reward:{points_cost:200,discount_cents:500,min_order_cents:3000},
};
const run=(changes:Partial<typeof base>={})=>simulateTrial({...base,...changes});

describe("laboratório local do programa sem escrita financeira",()=>{
  it("simula compra paga e resgate elegível, sem fingir uso de cupom",()=>{
    expect(run()).toEqual({
      earnedPoints:200,pendingPoints:0,availablePoints:200,
      redeemedPoints:200,remainingPoints:0,discountCents:500,
      eligibleInSimulation:true,reason:"eligible",
    });
  });
  it("separa pedido não pago, carência, estorno e expiração",()=>{
    expect(run({payment:"pending"})).toMatchObject({
      earnedPoints:0,availablePoints:0,discountCents:0,reason:"no_payment",
    });
    expect(run({payment:"reversed"})).toMatchObject({
      earnedPoints:0,availablePoints:0,discountCents:0,reason:"reversed",
    });
    expect(run({stage:"waiting"})).toMatchObject({
      earnedPoints:200,pendingPoints:200,availablePoints:0,
      discountCents:0,reason:"hold",
    });
    expect(run({stage:"expired"})).toMatchObject({
      earnedPoints:200,pendingPoints:0,availablePoints:0,
      discountCents:0,reason:"expired",
    });
  });
  it("bloqueia recompensa quando saldo ou valor de checkout não basta",()=>{
    expect(run({eligiblePurchaseCents:19900})).toMatchObject({
      availablePoints:199,discountCents:0,reason:"no_points",
    });
    expect(run({checkoutCents:2900})).toMatchObject({
      availablePoints:200,discountCents:0,reason:"order_minimum",
    });
  });
  it("sem configuração nunca inventa crédito ou resgate",()=>{
    expect(run({rule:null})).toMatchObject({
      earnedPoints:0,discountCents:0,reason:"no_rule",
    });
    expect(run({reward:null})).toMatchObject({
      earnedPoints:200,discountCents:0,reason:"no_reward",
    });
  });
  it("um pedido gera floor de pontos exatamente como a regra",()=>{
    expect(run({eligiblePurchaseCents:417,
      rule:{points:3,per_cents:250,hold_days:7,validity_days:180},
      reward:{points_cost:5,discount_cents:100,min_order_cents:100},
    })).toMatchObject({
      earnedPoints:5,availablePoints:5,discountCents:100,
    });
  });
  it("impede valores inválidos, NaN e quantidades gigantes",()=>{
    for(const value of [-1,NaN,Infinity,1.2,100_000_001]){
      expect(run({eligiblePurchaseCents:value})).toBeNull();
      expect(run({checkoutCents:value})).toBeNull();
    }
    expect(run({rule:{...base.rule,per_cents:0}})).toMatchObject({
      reason:"no_rule",discountCents:0,
    });
    expect(run({reward:{...base.reward,discount_cents:6000}})).toMatchObject({
      reason:"no_reward",discountCents:0,
    });
    expect(run({eligiblePurchaseCents:100_000_000,
      rule:{...base.rule,points:100_000,per_cents:100}})).toBeNull();
  });
});
