import {describe,it,expect} from "vitest";
import {estimateReward} from "./reward-economics";

describe("prévia de custo de recompensa (sem lançamento financeiro)",()=>{
  it("relaciona regra de pontos e recompensa por centavos inteiros",()=>{
    expect(estimateReward(200,500,50,{points:1,per_cents:100})).toEqual({
      eligibleSpendCents:20000,benefitRateBps:250,
      nominalExposureCents:25000,
    });
  });
  it("inverte corretamente o floor do motor de pontos",()=>{
    const estimate=estimateReward(5,100,2,{points:3,per_cents:250});
    expect(estimate?.eligibleSpendCents).toBe(417);
    expect(Math.floor(416*3/250)).toBe(4);
    expect(Math.floor(estimate!.eligibleSpendCents!*3/250)).toBe(5);
  });
  it("não inventa gasto nem taxa sem regra publicada no rascunho",()=>{
    expect(estimateReward(200,500,50,null)).toEqual({
      eligibleSpendCents:null,benefitRateBps:null,nominalExposureCents:25000,
    });
  });
  it("mantém exposição nominal mesmo quando o gasto teórico excede limite",()=>{
    expect(estimateReward(1_000_000,500,50,{points:1,per_cents:100_000_000})).toEqual({
      eligibleSpendCents:null,benefitRateBps:null,nominalExposureCents:25000,
    });
  });
  it("rejeita campos inválidos em vez de converter vazio, float ou boolean",()=>{
    for(const [points,amount,limit] of [
      [0,500,50],[200,0,50],[200,500,0],[2.5,500,50],
      [200,500,1e8],[-1,500,50],[200,500.4,50],[NaN,500,50],
    ])expect(estimateReward(points,amount,limit,{points:1,per_cents:100})).toBeNull();
    expect(estimateReward(200,500,50,{points:0,per_cents:100})).toEqual({
      eligibleSpendCents:null,benefitRateBps:null,nominalExposureCents:25000,
    });
  });
  it("expõe percentual muito alto para revisão, sem classificar margem como segura",()=>{
    const result=estimateReward(100,1500,100,{points:1,per_cents:100});
    expect(result?.benefitRateBps).toBe(15000);
    expect(result?.nominalExposureCents).toBe(150000);
    expect(result).not.toHaveProperty("approved");
  });
});
