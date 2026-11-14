import {expect,test,type Page} from "@playwright/test";
const store={id:"be9f41dc-a675-4d33-9958-20c62268b2c7",
 name:"Loja Fideliza QA",slug:"qa-fideliza",status:"active",role:"owner"};
async function mock(page:Page){
 await page.route("**/api/v1/auth/session/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   authenticated:true,user:{username:"qa-owner",display_name:"QA Lojista"},
   tenants:[store],
  }),
 }));
 await page.route("**/api/v1/tenants/**/nuvemshop/status/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   configured:true,connected:true,
   order_verification:{
    order_scope_granted:false,preview_enabled:false,
    read_only_preview_available:false,live_cashback_enabled:false,
    signed_event_inbox_enabled:false,event_receipt_does_not_verify_payment:true,
   },
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
 await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   source:"verified_opt_in_only",data_status:"no_enrollment_channel",
   summary:{total:0,active:0,paused:0},items:[],limit:20,offset:0,total_filtered:0,
  }),
 }));
 await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"manual_review_only",points_credited:false,items:[],
  }),
 }));
}
for(const width of [320,390,1440]){
 test("Programa navega por objetivos e informa estado real de OAuth em "+width+"px",async({page},info)=>{
  await page.setViewportSize({width,height:850});await mock(page);
  const writes:string[]=[];
  page.on("request",request=>{
   if(request.url().includes("/api/v1/")&&
      !["GET","HEAD","OPTIONS"].includes(request.method()))writes.push(request.url());
  });
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
  await expect(page.getByRole("heading",{name:"Seu clube em três passos."})).toBeVisible();
  await expect(page.getByText("Autorização Nuvemshop registrada")).toBeVisible();
  await expect(page.getByText("Permissão de pedidos pendente",{exact:false})).toBeVisible();
  const navigation=page.getByRole("navigation",{name:"Áreas do programa"});
  await expect(navigation.getByRole("button",{name:"Benefícios"})).toHaveAttribute("aria-pressed","true");
  await expect(page.getByRole("heading",{name:"Benefícios do seu clube"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toBeVisible();
  await navigation.getByRole("button",{name:"Participantes"}).click();
  await expect(page.getByRole("heading",{name:"Entrada de participantes"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toHaveCount(0);
  await navigation.getByRole("button",{name:"Testes"}).click();
  await expect(page.getByRole("heading",{name:"Validar antes de ativar"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Acompanhar pedidos"})).toBeVisible();
  await expect(page.getByText("Testar pontos e recompensas sem publicar")).toBeVisible();
  await page.getByRole("button",{name:"Acompanhar pedidos"}).click();
  await expect(page.getByRole("navigation",{name:"Canais de vendas"})).toBeVisible();
  expect(writes).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
   .toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath("program-navigation-"+width+".png"),fullPage:true});
 });
}
