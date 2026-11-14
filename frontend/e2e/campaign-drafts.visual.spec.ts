import {expect,test,type Page,type Route} from "@playwright/test";

const tenant={
 id:"e130da1e-42a5-4957-ae39-129fce907b2c",
 name:"Loja QA",slug:"qa",status:"active",role:"owner"
};
const draftId="909c803e-63a1-4a47-8c62-bef8727500f7";
async function mockSession(page:Page){
 await page.context().addCookies([{name:"csrftoken",value:"qa-only-csrf",url:"http://127.0.0.1:4173"}]);
 await page.route("**/api/v1/auth/session/",r=>r.fulfill({
  contentType:"application/json",
  body:JSON.stringify({authenticated:true,
    user:{username:"qa-owner",display_name:"Usuário QA"},tenants:[tenant]}),
 }));
 await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
  contentType:"application/json",
  body:JSON.stringify({source:"verified_opt_in_only",data_status:"no_enrollment_channel",
    summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,
    items:[],note:"Sem participantes."}),
 }));
 await page.route("**/api/v1/tenants/**/nuvemshop/status/",r=>r.fulfill({
  contentType:"application/json",
  body:JSON.stringify({configured:false,connected:false,store_id:null,
    scope:null,mode:"read_products_only",ready_for_write:false}),
 }));
}

for(const width of [390,768,1440]){
 test("Campanha de pontos segura e responsiva em "+width+"px",async({page})=>{
  const drafts:Array<Record<string,unknown>>=[];
  await page.setViewportSize({width,height:850});
  await mockSession(page);
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/",async(route:Route)=>{
   if(route.request().method()==="GET"){
    return route.fulfill({contentType:"application/json",body:JSON.stringify({
     mode:"draft_only",activation_available:false,items:drafts,
    })});
   }
   if(route.request().method()==="POST"){
    const data=route.request().postDataJSON();
    expect(data).toEqual({goal:"second_purchase",bonus_points:20,max_customers:40});
    const item={...data,id:draftId,status:"draft",published:false,
     sending_enabled:false,maximum_bonus_points:800};
    drafts.unshift(item);
    return route.fulfill({status:201,contentType:"application/json",body:JSON.stringify({
      mode:"draft_only",campaign:item,points_credited:false,messages_sent:false,
    })});
   }
   return route.fulfill({status:405});
  });
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:/^Campanhas/}).click();
  await expect(page.getByRole("heading",{name:"O que você quer incentivar?"})).toBeVisible();
  await page.getByRole("button",{name:"Continuar"}).click();
  await page.getByRole("spinbutton",{name:"Pontos extras por pessoa"}).fill("20");
  await page.getByRole("spinbutton",{name:"Número máximo de pessoas"}).fill("40");
  await page.getByRole("button",{name:"Revisar campanha"}).click();
  await expect(page.getByRole("heading",{name:"Sua campanha, antes de publicar"})).toBeVisible();
  await expect(page.getByText("800 pontos",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"Guardar rascunho"}).click();
  await expect(page.getByText("Rascunho salvo. Nenhuma mensagem foi enviada",{exact:false})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Rascunhos salvos"})).toBeVisible();
  await expect(page.getByText("20 pontos extras",{exact:false})).toBeVisible();
  expect(await page.getByRole("button",{name:/Publicar|Ativar campanha/}).count()).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
   .toBeLessThanOrEqual(1);
 });
}

test("Início usa rascunho de pontos e não apresenta cashback antigo",async({page})=>{
 await mockSession(page);
 await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   mode:"draft_only",activation_available:false,
   items:[{id:draftId,goal:"second_purchase",bonus_points:30,
    max_customers:20,maximum_bonus_points:600,status:"draft",
    published:false,sending_enabled:false}],
  }),
 }));
 await page.goto("/");
 await expect(page.getByRole("heading",{name:"Retome seu planejamento"})).toBeVisible();
 await expect(page.getByText("Nenhuma campanha foi publicada.",{exact:false})).toBeVisible();
 await page.getByRole("button",{name:"Ver planejamento"}).click();
 await expect(page.getByRole("heading",{name:"Rascunhos salvos"})).toBeVisible();
 await expect(page.getByText("30 pontos extras",{exact:false})).toBeVisible();
 expect(await page.getByRole("button",{name:/Publicar|Ativar/}).count()).toBe(0);
});
