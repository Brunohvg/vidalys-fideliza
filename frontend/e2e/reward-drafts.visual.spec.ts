import {expect,test,type Page,type Route} from "@playwright/test";

const store={id:"95eb6b31-27cf-4adb-af35-642ac8767385",
 name:"Loja Resgate QA",slug:"loja-resgate-qa",status:"active",role:"owner"};

async function setup(page:Page){
 await page.context().addCookies([{
  name:"csrftoken",value:"reward-csrf-test",url:"http://127.0.0.1:4173",
 }]);
 await page.route("**/api/v1/auth/session/",route=>route.fulfill({
  contentType:"application/json",body:JSON.stringify({
   authenticated:true,user:{username:"reward-owner",display_name:"Lojista QA"},
   tenants:[store],
  }),
 }));
 await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   source:"verified_opt_in_only",data_status:"consent_verified",
   summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,
   items:[],note:"Sem adesões",
  }),
 }));
 await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,rule:null,
  }),
 }));
}

const id="b78f99bd-cbc0-4eaf-8f73-558e54b72a93";

async function openTiers(page:Page,width:number){
 await page.goto("/app/visao-geral");
 if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
 await page.locator(".portal-nav").getByRole("button",{name:"Meu clube",exact:true}).click();
 await page.getByRole("tab",{name:"2. Como usar"}).click();
}

for(const width of [390,1440]){
 test("Nova faixa usa o preço do ponto e não cria cupom em "+width+"px",async({page},info)=>{
  await page.setViewportSize({width,height:850});
  await setup(page);
  const saved:Array<Record<string,unknown>>=[];
  let calls=0;
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",async(route:Route)=>{
   if(route.request().method()==="GET")return route.fulfill({contentType:"application/json",
    body:JSON.stringify({mode:"draft_only",activation_available:false,items:saved})});
   calls++;
   const data=route.request().postDataJSON();
   expect(data).toEqual({title:"R$ 10 de desconto",points_cost:1000,discount_cents:1000,
    min_order_cents:3000,max_redemptions:1000});
   expect(route.request().headers()["x-csrftoken"]).toBe("reward-csrf-test");
   const reward={...data,id,status:"draft",published:false,redemption_enabled:false};
   saved.unshift(reward);
   return route.fulfill({status:201,contentType:"application/json",
    body:JSON.stringify({mode:"draft_only",reward,coupon_created:false,points_credited:false})});
  });
  await openTiers(page,width);
  await expect(page.getByText("Nenhuma faixa ainda")).toBeVisible();
  await page.getByRole("button",{name:"Nova faixa"}).click();
  await page.getByRole("group",{name:"Valor do desconto"}).getByRole("button",{name:"R$ 10"}).click();
  await expect(page.getByText("1.000 pontos",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"Criar faixa"}).click();
  await expect(page.getByText("Faixa criada como rascunho.",{exact:false})).toBeVisible();
  await expect(page.locator(".vf-tier")).toHaveCount(1);
  await expect(page.locator(".vf-tier")).toContainText("Rascunho");
  expect(calls).toBe(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath("tiers-"+width+".png"),fullPage:true});
 });
}

test("Pedido mínimo menor que o desconto é recusado sem chamar a API",async({page})=>{
 await page.setViewportSize({width:390,height:850});
 await setup(page);
 let posts=0;
 await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",route=>{
  if(route.request().method()!=="GET")posts++;
  return route.fulfill({contentType:"application/json",body:JSON.stringify({mode:"draft_only",activation_available:false,items:[]})});
 });
 await openTiers(page,390);
 await page.getByRole("button",{name:"Nova faixa"}).click();
 await page.getByRole("textbox",{name:"Pedido mínimo (R$)"}).fill("5,00");
 await page.getByRole("button",{name:"Criar faixa"}).click();
 await expect(page.getByRole("alert")).toContainText("pedido mínimo precisa ser igual ou maior");
 expect(posts).toBe(0);
});

for(const width of [390,1440]){
 test("Publica, cancela, despublica e exclui faixa sem criar cupom em "+width+"px",async({page})=>{
  await page.setViewportSize({width,height:850});
  await setup(page);
  let calls=0,deleted=false;
  let reward={id,title:"R$ 5 de desconto",points_cost:500,discount_cents:500,min_order_cents:3000,max_redemptions:2,
   status:"draft" as "draft"|"published",published:false,redemption_enabled:false,published_at:null as null|string};
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",route=>route.fulfill({contentType:"application/json",
   body:JSON.stringify({mode:"draft_only",activation_available:false,items:deleted?[]:[reward]})}));
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/"+id+"/publication/",route=>{
   calls++;
   expect(route.request().method()).toBe("PATCH");
   expect(route.request().headers()["x-csrftoken"]).toBe("reward-csrf-test");
   const {published}=route.request().postDataJSON();
   reward={...reward,published,status:published?"published":"draft",published_at:published?"2026-11-14T00:00:00Z":null};
   return route.fulfill({contentType:"application/json",body:JSON.stringify({reward,catalog_published:published,
    redemption_enabled:false,coupon_created:false,points_credited:false,points_debited:false})});
  });
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/"+id+"/",route=>{
   expect(route.request().method()).toBe("DELETE");deleted=true;
   return route.fulfill({contentType:"application/json",body:JSON.stringify({deleted:true,id})});
  });
  await openTiers(page,width);
  const card=page.locator(".vf-tier");
  await card.getByRole("button",{name:"Publicar",exact:true}).click();
  await expect(card.getByText("Publicar no Meu Clube?")).toBeVisible();
  await card.getByRole("button",{name:"Não"}).click();
  expect(calls,"cancelar publicação não pode fazer PATCH").toBe(0);
  await card.getByRole("button",{name:"Publicar",exact:true}).click();
  await card.getByRole("button",{name:"Publicar",exact:true}).click();
  await expect(page.getByText("Faixa publicada no Meu Clube.",{exact:false})).toBeVisible();
  await expect(card.getByText("Publicada")).toBeVisible();
  await card.getByRole("button",{name:"Despublicar"}).click();
  await expect(page.getByText("Faixa despublicada.",{exact:false})).toBeVisible();
  expect(calls).toBe(2);
  await card.getByRole("button",{name:"Excluir R$ 5 de desconto"}).click();
  await card.getByRole("button",{name:"Excluir",exact:true}).click();
  await expect(page.getByText("Nenhuma faixa ainda")).toBeVisible();
  expect(deleted).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
 });
}
