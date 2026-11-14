import {expect,test,type Page} from "@playwright/test";

const shop={
 id:"de8203a3-52e1-4927-ab39-bec1e3842f32",
 name:"Loja QA Pedidos",slug:"qa-pedidos",status:"active",role:"owner",
};
const order={
 order_id:"1234567",source:"nuvemshop_live_read_only",
 order_status:"open",payment_status:"paid",
 paid_at:"2026-11-14T01:00:00Z",
 reported_total_cents:20000,currency:"BRL",
 reported_customer_paid_cents:20000,
 reported_payment_differs_from_total:false,
 reported_paid_amount_is_not_psp_proof:true,
 participant_verified:true,
 review_status:"reported_paid_requires_reconciliation",
 credit_eligible:false,cashback_created:false,writes_performed:0,
 note:"Pagamento reportado ainda exige conciliação, reversões e auditoria.",
};
async function setup(page:Page){
 await page.context().addCookies([{name:"csrftoken",value:"no-financial-writes",
  url:"http://127.0.0.1:4173"}]);
 await page.route("**/api/v1/auth/session/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   authenticated:true,user:{username:"qa",display_name:"Operador QA"},
   tenants:[shop],
  }),
 }));
 await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   source:"verified_opt_in_only",data_status:"consent_verified",
   summary:{total:0,active:0,paused:0},
   total_filtered:0,limit:20,offset:0,items:[],note:"Sem participantes",
  }),
 }));
 await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,rule:null,
  }),
 }));
 await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,items:[],
  }),
 }));
}
for(const width of [320,390,1440]){
 test("Pedido Nuvemshop real tem diagnóstico sem gerar pontos em "+width+"px",async({page},info)=>{
  await page.setViewportSize({width,height:880});
  await setup(page);
  let count=0;const writes:string[]=[];
  page.on("request",req=>{
   if(req.url().includes("/api/v1/")&&!["GET","OPTIONS","HEAD"].includes(req.method()))
    writes.push(req.url());
  });
  await page.route("**/api/v1/tenants/**/nuvemshop/orders/1234567/preview/",r=>{
   count++;
   expect(r.request().method()).toBe("GET");
   return r.fulfill({contentType:"application/json",body:JSON.stringify(order)});
  });
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
  await page.getByText("Conferir pedido Nuvemshop antes de liberar pontos").click();
  await expect(page.getByRole("heading",{name:"Conferir uma compra na Nuvemshop"})).toBeVisible();
  const input=page.getByRole("textbox",{name:"ID interno do pedido na Nuvemshop"});
  await input.fill("abc");
  await expect(page.getByRole("button",{name:"Conferir pedido"})).toBeDisabled();
  await input.fill("1234567");
  await page.getByRole("button",{name:"Conferir pedido"}).click();
  const result=page.getByRole("region",{name:"Resultado da conferência do pedido"});
  await expect(result).toContainText("Falta conciliação financeira");
  await expect(result).toContainText("R$ 200,00");
  await expect(result).toContainText("Vinculado");
  await expect(result).toContainText("Nenhum ponto foi criado");
  expect(count).toBe(1);
  expect(writes).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
   .toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath("order-check-"+width+".png"),fullPage:true});
 });
}
test("Pedido cancelado ou com API indisponível não libera pontos",async({page})=>{
 await page.setViewportSize({width:390,height:840});await setup(page);
 await page.route("**/api/v1/tenants/**/nuvemshop/orders/1234567/preview/",r=>
  r.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
   ...order,order_status:"cancelled",payment_status:"refunded",
   review_status:"blocked_cancelled",
  })}));
 await page.route("**/api/v1/tenants/**/nuvemshop/orders/987654/preview/",r=>
  r.fulfill({status:409,contentType:"application/json",body:JSON.stringify({
   detail:"Autorize a leitura de pedidos nesta loja.",
  })}));
 await page.goto("/");
 await page.getByRole("button",{name:"Abrir menu"}).click();
 await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
 await page.getByText("Conferir pedido Nuvemshop antes de liberar pontos").click();
 const input=page.getByRole("textbox",{name:"ID interno do pedido na Nuvemshop"});
 await input.fill("1234567");await page.getByRole("button",{name:"Conferir pedido"}).click();
 await expect(page.getByRole("region",{name:"Resultado da conferência do pedido"}))
  .toContainText("Pedido cancelado");
 await input.fill("987654");await page.getByRole("button",{name:"Conferir pedido"}).click();
 await expect(page.locator(".vf-order-check-error")).toContainText("permissão read_orders");
 await expect(page.getByRole("region",{name:"Resultado da conferência do pedido"})).toHaveCount(0);
});
