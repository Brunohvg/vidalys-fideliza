import {describe,expect,it} from "vitest";
import {pointValueText,summarizeClub} from "./club-summary";

const rule={points:1,per_cents:100,hold_days:7,validity_days:180};
const reward=(title:string,points_cost:number,discount_cents:number,published=true)=>
  ({title,points_cost,discount_cents,published});

describe("Seu clube em uma frase",()=>{
  it("explica a regra e a porcentagem devolvida com uma recompensa",()=>{
    const result=summarizeClub(rule,[reward("R$ 10 de desconto",500,1000)]);
    expect(result.sentences[0]).toMatch(/^A cada R\$\s1,00 em compras, o cliente ganha 1 ponto\.$/);
    expect(result.sentences[1]).toContain("7 dias depois da compra paga");
    expect(result.sentences[2]).toMatch(/500 pontos viram R\$\s10,00 de desconto \(cerca de R\$\s500,00 em compras\)\./);
    expect(result.sentences[3]).toBe("Na prática, o cliente recebe 2% de volta.");
    expect(result.returnBps).toEqual({min:200,max:200});
    expect(result.stage).toBe("ready");
    expect(result.warnings).toEqual([]);
  });

  it("carência zero e pluralização",()=>{
    const result=summarizeClub({...rule,points:2,hold_days:0,validity_days:1},[reward("Brinde",100,200)]);
    expect(result.sentences[0]).toContain("ganha 2 pontos");
    expect(result.sentences[1]).toBe("Os pontos ficam disponíveis logo após a compra paga e valem por 1 dia.");
  });

  it("avisa quando as recompensas dão valores diferentes ao ponto",()=>{
    const result=summarizeClub(rule,[reward("A",500,1000),reward("B",1000,5000)]);
    expect(result.pointValue).toEqual({min:200,max:500});
    expect(result.returnBps).toEqual({min:200,max:500});
    expect(result.sentences.at(-1)).toBe("Na prática, o cliente recebe de 2% a 5% de volta, conforme a recompensa.");
    expect(result.warnings.map(w=>w.key)).toEqual(["inconsistent_value"]);
    expect(result.warnings[0].text).toMatch(/de R\$\s0,02 a R\$\s0,05/);
  });

  it("não acusa diferença pequena de arredondamento",()=>{
    const result=summarizeClub(rule,[reward("A",500,1000),reward("B",450,1000)]);
    expect(result.warnings).toEqual([]);
  });

  it("alerta devolução acima de 10%",()=>{
    const result=summarizeClub(rule,[reward("Generosa",100,1500)]);
    expect(result.warnings.map(w=>w.key)).toContain("high_rate");
  });

  it("sem regra ou sem recompensa fica em montagem e diz o que falta",()=>{
    const empty=summarizeClub(null,[]);
    expect(empty.stage).toBe("setup");
    expect(empty.warnings.map(w=>w.key)).toEqual(["no_rule","no_reward"]);
    expect(empty.returnBps).toBeNull();
    const draftOnly=summarizeClub(rule,[reward("Rascunho",500,1000,false)]);
    expect(draftOnly.stage).toBe("setup");
    expect(draftOnly.returnBps).toEqual({min:200,max:200});
  });

  it("usa só as publicadas quando existem",()=>{
    const result=summarizeClub(rule,[reward("Pub",500,1000),reward("Rascunho",100,5000,false)]);
    expect(result.returnBps).toEqual({min:200,max:200});
  });

  it("formata valor de ponto menor que um centavo",()=>{
    expect(pointValueText(100)).toMatch(/R\$\s0,01$/);
    expect(pointValueText(50)).toMatch(/R\$\s0,005$/);
  });
});
