import {expect,test,type Page,type Route} from "@playwright/test";

/* Campanhas inteligentes: modelos com público real, custo máximo ao vivo,
   grupo de comparação, prévia do cartão no Meu Clube e publicação sem crédito. */

const tenant={id:"a5ee4147-b23c-4ad2-ae44-c3f5aaf13ed0",name:"Loja de teste",slug:"loja-teste",status:"active",role:"owner"};
const id="b26c657d-c802-4757-a4e6-ec71ec53c582";
const audience=(reached:number,bonus:number,eligible=reached)=>({eligible,reached,comparison:Math.round(eligible*0.1),
  max_cost_cents:reached*bonus,max_cost_if_full_cents:100*bonus});

function campaign(over:Record<string,unknown>={}){
  return {id,goal:"reactivation",bonus_points:200,max_customers:100,maximum_bonus_points:20000,
    title:"",message:"",display_title:"Sentimos sua falta: +200 pontos",display_message:"Compre até 30/11 e ganhe 200 pontos extras.",
    starts_on:"2026-11-18",ends_on:"2026-12-03",window_days:30,inactive_days:60,near_points:100,multiplier:2,holdout_percent:10,
    status:"draft",published:false,published_at:null,sending_enabled:false,points_credited:false,
    audience:audience(36,200,40),result:null,...over};
}

async function setup(page:Page,items:Record<string,unknown>[]=[]){
  await page.context().addCookies([{name:"csrftoken",value:"campaign-csrf",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    authenticated:true,user:{username:"qa",display_name:"QA"},tenants:[tenant]})}));
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/audience/",async(route:Route)=>{
    const data=route.request().postDataJSON();
    const counts:Record<string,number>={second_purchase:12,reactivation:40,near_reward:0,multiplier:250,birthday:3,recurrence:250};
    const eligible=counts[data.goal]??0;
    const reached=Math.min(Math.round(eligible*(1-(data.holdout_percent??10)/100)),data.max_customers);
    return route.fulfill({contentType:"application/json",body:JSON.stringify({audience:audience(reached,data.bonus_points,eligible),saved:false})});
  });
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/",async(route:Route)=>{
    if(route.request().method()==="GET")
      return route.fulfill({contentType:"application/json",body:JSON.stringify({mode:"offer_only",activation_available:false,items})});
    const data=route.request().postDataJSON();
    const item=campaign({...data,audience:audience(36,data.bonus_points,40)});
    items.unshift(item);
    return route.fulfill({status:201,contentType:"application/json",body:JSON.stringify({mode:"draft_only",campaign:item,points_credited:false,messages_sent:false})});
  });
}
const open=async(page:Page,width:number)=>{
  await page.goto("/app/visao-geral");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:/^Campanhas/}).click();
};
const noOverflow=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);

for(const width of [320,390,768,1440]){
  test("Nova campanha mostra público real, custo e prévia do cliente em "+width+"px",async({page},testInfo)=>{
    await page.setViewportSize({width,height:width<=390?844:900});
    let published=false;let saved:Record<string,unknown>|null=null;
    await setup(page);
    await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/"+id+"/publish/",r=>{published=true;
      return r.fulfill({contentType:"application/json",body:JSON.stringify({campaign:campaign({status:"live",published:true}),points_credited:false,messages_sent:false})});});
    page.on("request",req=>{if(req.method()==="POST"&&/point-campaign-drafts\/$/.test(req.url()))saved=req.postDataJSON();});
    await open(page,width);
    await page.getByRole("button",{name:"Nova campanha"}).click();
    await expect(page.getByRole("heading",{name:"Qual é o objetivo?"})).toBeVisible();
    await expect(page.getByRole("button",{name:/Trazer de volta.*40 clientes hoje/})).toBeVisible();
    await noOverflow(page);
    await page.screenshot({path:testInfo.outputPath("campaign-models-"+width+".png"),fullPage:true});
    await page.getByRole("button",{name:/Trazer de volta/}).click();
    await expect(page.getByRole("heading",{name:"Quanto de bônus?"})).toBeVisible();
    await page.getByRole("button",{name:"90 dias"}).click();
    await page.getByRole("spinbutton",{name:"Pontos extras por pessoa"}).fill("250");
    await page.getByRole("spinbutton",{name:"Número máximo de pessoas"}).fill("100");
    const panel=page.getByRole("complementary",{name:"Público e custo"});
    await expect(panel).toContainText("36");
    await expect(panel).toContainText("R$ 90,00");
    await page.getByRole("button",{name:"Próximo"}).click();
    await expect(page.getByRole("heading",{name:"Quando?"})).toBeVisible();
    await page.getByRole("button",{name:"7 dias"}).click();
    const phone=page.getByRole("complementary",{name:"Como o cliente vê no Meu Clube"});
    await expect(phone).toContainText("Sentimos sua falta: +250 pontos");
    await expect(phone).toContainText("Os pontos entram quando a loja ativar o clube.");
    await noOverflow(page);
    await page.screenshot({path:testInfo.outputPath("campaign-when-"+width+".png"),fullPage:true});
    await page.getByRole("button",{name:"Próximo"}).click();
    await expect(page.getByRole("heading",{name:"Revise antes de publicar"})).toBeVisible();
    await expect(page.getByText("Nenhum ponto é creditado e nada é enviado",{exact:false})).toBeVisible();
    await page.getByRole("button",{name:"Publicar no Meu Clube"}).click();
    await expect(page.getByText("Campanha publicada no Meu Clube.",{exact:false})).toBeVisible();
    expect(published).toBe(true);
    expect(saved).toMatchObject({goal:"reactivation",bonus_points:250,max_customers:100,inactive_days:90,holdout_percent:10});
    await expect(page.getByText("No Meu Clube",{exact:true})).toBeVisible();
    await noOverflow(page);
  });
}

test("Lista mostra resultado contra o grupo de comparação e permite tirar do ar",async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:900});
  await setup(page,[campaign({status:"live",published:true,published_at:"2026-11-10T12:00:00Z",
    result:{reached:120,reached_returned:30,comparison:40,comparison_returned:4}})]);
  let unpublished=false;
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/"+id+"/publish/",r=>{unpublished=!r.request().postDataJSON().published;
    return r.fulfill({contentType:"application/json",body:JSON.stringify({campaign:campaign({status:"draft"}),points_credited:false,messages_sent:false})});});
  await open(page,1440);
  const result=page.getByLabel("Resultado da campanha");
  await expect(result).toContainText("25%");
  await expect(result).toContainText("10%");
  await expect(result).toContainText("Diferença de 15 pontos percentuais");
  await page.screenshot({path:testInfo.outputPath("campaign-list-1440.png"),fullPage:true});
  await page.getByRole("button",{name:"Tirar do Meu Clube"}).click();
  await expect(page.getByText("Campanha tirada do Meu Clube.",{exact:false})).toBeVisible();
  expect(unpublished).toBe(true);
});

test("Campanha salva pode ser editada e excluída",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await setup(page,[campaign()]);
  let patched:Record<string,unknown>|null=null;let removed=false;
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/"+id+"/",r=>{
    if(r.request().method()==="DELETE"){removed=true;return r.fulfill({contentType:"application/json",body:JSON.stringify({deleted:true,id})});}
    patched=r.request().postDataJSON();
    return r.fulfill({contentType:"application/json",body:JSON.stringify({mode:"draft_only",campaign:campaign({bonus_points:500}),messages_sent:false})});
  });
  await open(page,390);
  await page.getByRole("button",{name:"Editar"}).click();
  await page.getByRole("button",{name:"500 pontos"}).click();
  await page.getByRole("button",{name:"Próximo"}).click();
  await page.getByRole("button",{name:"Próximo"}).click();
  await page.getByRole("button",{name:"Salvar rascunho"}).click();
  await expect(page.getByText("Campanha salva como rascunho.",{exact:false})).toBeVisible();
  expect(patched).toMatchObject({bonus_points:500,goal:"reactivation"});
  await page.getByRole("button",{name:"Excluir"}).click();
  await page.getByRole("button",{name:"Confirmar exclusão"}).click();
  await expect(page.getByText("Campanha excluída.",{exact:false})).toBeVisible();
  expect(removed).toBe(true);
});

test("Analista vê campanhas sem poder criar ou publicar",async({page})=>{
  await page.context().addCookies([{name:"csrftoken",value:"campaign-csrf",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    authenticated:true,user:{username:"qa",display_name:"QA"},tenants:[{...tenant,role:"analyst"}]})}));
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify({mode:"offer_only",activation_available:false,items:[campaign()]})}));
  await open(page,1440);
  await expect(page.getByRole("heading",{name:"Suas campanhas"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Nova campanha"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Publicar"})).toHaveCount(0);
});
