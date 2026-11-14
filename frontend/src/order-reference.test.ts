import {describe,it,expect} from "vitest";
import {parseOrderReference} from "./order-reference";
describe("referências de pedidos Nuvemshop",()=>{
  it("aceita o número visível com ou sem #",()=>{
    expect(parseOrderReference("#14111")).toMatchObject({kind:"number",value:"14111"});
    expect(parseOrderReference(" 14111 ")).toMatchObject({kind:"number",value:"14111"});
  });
  it("extrai id apenas do caminho administrativo de URL oficial",()=>{
    expect(parseOrderReference("https://bibelo8.lojavirtualnuvem.com.br/admin/orders/2120958234"))
      .toMatchObject({kind:"id",value:"2120958234",source:"link"});
    expect(parseOrderReference("https://admin.nuvemshop.com.br/admin/orders/2120958234?from=dashboard"))
      .toMatchObject({kind:"id",value:"2120958234",source:"link"});
  });
  it("números avulsos nunca mudam de tipo sem escolha explícita",()=>{
    expect(parseOrderReference("363573290")).toMatchObject({kind:"number",value:"363573290"});
    expect(parseOrderReference("363573290",true)).toMatchObject({kind:"id",value:"363573290"});
    expect(parseOrderReference("#14111",true)).toMatchObject({kind:"number",value:"14111"});
  });
  it("não transforma links externos ou códigos arbitrários em pedido",()=>{
    for(const value of [
      "https://evil.com/admin/orders/2120958234",
      "http://bibelo8.lojavirtualnuvem.com.br/admin/orders/2120958234",
      "https://bibelo8.lojavirtualnuvem.com.br/admin/orders/2120958234/edit",
      "https://user:pass@bibelo8.lojavirtualnuvem.com.br/admin/orders/2120958234",
      "#-1","14111/other","0","00012","1".repeat(19),"ab1234","",
    ])expect(parseOrderReference(value)).toBeNull();
  });
});
