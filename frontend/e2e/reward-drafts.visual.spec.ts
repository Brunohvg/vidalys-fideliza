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

for(const width of [390,1440]){
 test("Rascunho de desconto sem criar cupom ou pontos em "+width+"px",async({page},info)=>{
  await page.setViewportSize({width,height:850});
  await setup(page);
  const saved:Array<Record<string,unknown>>=[];
  let calls=0;
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",async(route:Route)=>{
   if(route.request().method()==="GET")return route.fulfill({
    contentType:"application/json",body:JSON.stringify({
     mode:"draft_only",activation_available:false,items:saved,
    }),
   });
   calls++;
   const data=route.request().postDataJSON();
   expect(data).toEqual({
    title:"R$ 5 de desconto",points_cost:200,discount_cents:500,
    min_order_cents:3000,max_redemptions:50,
   });
   expect(route.request().headers()["x-csrftoken"]).toBe("reward-csrf-test");
   const reward={...data,id:"b78f99bd-cbc0-4eaf-8f73-558e54b72a93",
    status:"draft",published:false,redemption_enabled:false};
   saved.unshift(reward);
   return route.fulfill({status:201,contentType:"application/json",
    body:JSON.stringify({mode:"draft_only",reward,
      coupon_created:false,points_credited:false}),
   });
  });
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
  await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toBeVisible();
  await expect(page.getByRole("region",{name:"Conferência da recompensa planejada"})).toHaveCount(0);
  await expect(page.getByLabel("Conferência da recompensa planejada")).toContainText(
    "Salve uma regra de pontos");
  await expect(page.getByLabel("Conferência da recompensa planejada"))
    .toContainText("R$ 250,00");
  await page.getByPlaceholder("Ex.: R$ 5 de desconto").fill("R$ 5 de desconto");
  await page.getByRole("spinbutton",{name:"Pontos necessários"}).fill("200");
  await page.getByRole("textbox",{name:"Valor do desconto (R$)"}).fill("5,00");
  await page.getByRole("button",{name:"Criar rascunho"}).click();
  await expect(page.getByText("Rascunho salvo.",{exact:false})).toBeVisible();
  await expect(page.getByText("Sem cupom, sem resgate e sem consumo de pontos.")).toBeVisible();
  expect(calls).toBe(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
   .toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath("rewards-draft-"+width+".png"),fullPage:true});
 });
}


test("Recompensa existente pode ser editada e excluída com confirmação",async({page})=>{
 await page.setViewportSize({width:390,height:850});
 await setup(page);
 const id="b78f99bd-cbc0-4eaf-8f73-558e54b72a93";
 let reward={id,title:"R$ 5 de desconto",points_cost:200,
  discount_cents:500,min_order_cents:3000,max_redemptions:50,
  status:"draft",published:false,redemption_enabled:false};
 let deleted=false,patched=false;
 await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,items:deleted?[]:[reward],
  }),
 }));
 await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/"+id+"/",r=>{
  expect(r.request().headers()["x-csrftoken"]).toBe("reward-csrf-test");
  if(r.request().method()==="PATCH"){
   patched=true;reward={...reward,...r.request().postDataJSON()};
   return r.fulfill({contentType:"application/json",body:JSON.stringify({
    mode:"draft_only",reward,coupon_created:false,
   })});
  }
  expect(r.request().method()).toBe("DELETE");
  deleted=true;
  return r.fulfill({contentType:"application/json",body:JSON.stringify({
   deleted:true,id,coupon_created:false,
  })});
 });
 await page.goto("/");
 await page.getByRole("button",{name:"Abrir menu"}).click();
 await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
 await page.getByRole("button",{name:"Editar",exact:true}).click();
 await page.getByPlaceholder("Ex.: R$ 5 de desconto").fill("R$ 10 de desconto");
 await page.getByRole("button",{name:"Salvar alterações"}).click();
 await expect(page.getByText("R$ 10 de desconto",{exact:true})).toBeVisible();
 expect(patched).toBe(true);
 await page.getByRole("button",{name:"Excluir",exact:true}).click();
 await expect(page.getByRole("group",{name:"Confirmação de exclusão da recompensa"})).toBeVisible();
 await page.getByRole("button",{name:"Cancelar exclusão"}).click();
 expect(deleted,"cancelar não pode chamar DELETE").toBe(false);
 await expect(page.getByRole("group",{name:"Confirmação de exclusão da recompensa"})).toHaveCount(0);
 await page.getByRole("button",{name:"Excluir",exact:true}).click();
 await page.getByRole("button",{name:"Confirmar exclusão"}).click();
 await expect(page.getByText("Nenhuma recompensa definida.",{exact:false})).toBeVisible();
 expect(deleted).toBe(true);
 await expect(page.getByRole("button",{name:/Publicar/})).toHaveCount(0);
});

test("Recompensa mostra esforço real em pontos, taxa e orçamento sem publicar",async({page})=>{
 await page.setViewportSize({width:390,height:850});
 await setup(page);
 await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,
   rule:{version:1,points:1,per_cents:100,hold_days:7,validity_days:180},
  }),
 }));
 await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,items:[],
  }),
 }));
 await page.goto("/");
 await page.getByRole("button",{name:"Abrir menu"}).click();
 await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
 const economics=page.getByLabel("Conferência da recompensa planejada");
 await expect(economics).toContainText("R$ 200,00");
 await expect(economics).toContainText("2,5%");
 await expect(economics).toContainText("R$ 250,00");
 await expect(economics).toContainText("não comprova lucro");
 await page.getByRole("spinbutton",{name:"Pontos necessários"}).fill("1");
 await page.getByRole("textbox",{name:"Valor do desconto (R$)"}).fill("150,00");
 await expect(economics).toContainText("Revise essa combinação");
 await expect(page.getByRole("button",{name:/Publicar/})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
  .toBeLessThanOrEqual(1);
});
