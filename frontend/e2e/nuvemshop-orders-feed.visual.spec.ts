import {expect,test,type Page} from "@playwright/test";

const tenant={id:"de8203a3-52e1-4927-ab39-bec1e3842f32",
 name:"Loja Integrada QA",slug:"loja-integrada",status:"active",role:"owner"};
const order={
 order_id:"2120958234",order_number:"14111",
 source:"nuvemshop_live_read_only",order_status:"open",payment_status:"paid",
 paid_at:"2026-11-14T01:00:00Z",
 reported_total_cents:20000,currency:"BRL",
 reported_customer_paid_cents:20000,
 reported_payment_differs_from_total:false,
 reported_paid_amount_is_not_psp_proof:true,participant_verified:true,
 review_status:"reported_paid_requires_reconciliation",
 credit_eligible:false,cashback_created:false,writes_performed:0,
 note:"Ainda exige prova do gateway",
};
const mock=async(page:Page)=>{
 await page.route("**/api/v1/auth/session/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   authenticated:true,user:{username:"qa-merchant",display_name:"Lojista QA"},
   tenants:[tenant],
  }),
 }));
 await page.route("**/api/v1/tenants/**/nuvemshop/status/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   configured:true,connected:true,
   order_verification:{order_scope_granted:true,preview_enabled:true,
    read_only_preview_available:true,live_cashback_enabled:false,
    signed_event_inbox_enabled:false,event_receipt_does_not_verify_payment:true},
  }),
 }));
 await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"manual_review_only",points_credited:false,items:[],
  }),
 }));
 await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   source:"verified_opt_in_only",data_status:"consent_verified",
   summary:{total:0,active:0,paused:0},items:[],limit:20,offset:0,total_filtered:0,
  }),
 }));
};
for(const width of [320,390,1440]){
 test("Pedidos reais aparecem sem digitar ID e têm diagnóstico em "+width+"px",async({page},info)=>{
  await page.setViewportSize({width,height:900});await mock(page);
  const writes:string[]=[];
  page.on("request",req=>{
   if(req.url().includes("/api/v1/")&&
      !["GET","OPTIONS","HEAD"].includes(req.method()))writes.push(req.url());
  });
  let feeds=0,inspects=0;
  await page.route("**/api/v1/tenants/**/nuvemshop/orders/recent/preview/",r=>{
   feeds++;
   return r.fulfill({contentType:"application/json",body:JSON.stringify({
    mode:"read_only",source:"nuvemshop_live_read_only",
    items:[order,{...order,order_id:"2120958235",order_number:"14112",
     payment_status:"pending",paid_at:null,participant_verified:false,
     review_status:"not_paid"}],page:1,page_size:10,
    points_credited:false,coupons_created:false,read_only:true,
    note:"Sem crédito",
   })});
  });
  await page.route("**/api/v1/tenants/**/nuvemshop/orders/2120958234/preview/",r=>{
   inspects++;return r.fulfill({contentType:"application/json",body:JSON.stringify(order)});
  });
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:"Vendas"}).click();
  await page.getByRole("navigation",{name:"Canais de vendas"})
   .getByRole("button",{name:"Nuvemshop"}).click();
  const feed=page.getByRole("region",{name:"Pedidos recentes da Nuvemshop"});
  await expect(feed.getByText("#14111")).toBeVisible();
  await expect(feed.getByText("#14112")).toBeVisible();
  await expect(feed.getByText("Falta conciliação financeira")).toBeVisible();
  await expect(feed.getByText("Aguardando pagamento")).toBeVisible();
  await feed.locator("li").first().getByRole("button",{name:"Conferir"}).click();
  const updated=page.getByRole("region",{name:"Conferência atualizada do pedido"});
  await expect(updated).toContainText("#14111");
  await expect(updated).toContainText("Falta conciliação financeira");
  await expect(updated).toContainText("Consulta sem gravação");
  expect(feeds).toBeGreaterThanOrEqual(1);expect(inspects).toBe(1);
  expect(writes).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
   .toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath("orders-feed-"+width+".png"),fullPage:true});
 });
}

test("Sem read_orders, painel avisa e não inventa ausência de vendas",async({page})=>{
 await page.setViewportSize({width:390,height:850});await mock(page);
 await page.route("**/api/v1/tenants/**/nuvemshop/orders/recent/preview/",r=>
  r.fulfill({status:409,contentType:"application/json",body:JSON.stringify({
   detail:"Autorize a leitura de pedidos nesta loja.",
  })}));
 await page.goto("/");
 await page.getByRole("button",{name:"Abrir menu"}).click();
 await page.locator(".portal-nav").getByRole("button",{name:"Vendas"}).click();
 await page.getByRole("navigation",{name:"Canais de vendas"})
  .getByRole("button",{name:"Nuvemshop"}).click();
 const feed=page.getByRole("region",{name:"Pedidos recentes da Nuvemshop"});
 await expect(feed).toContainText("precisa de read_orders");
 await expect(feed.getByText("Nenhum pedido retornado")).toHaveCount(0);
});
