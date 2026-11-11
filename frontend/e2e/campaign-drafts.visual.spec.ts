import {expect,test,type Page,type Route} from "@playwright/test";

const tenant={
 id:"e130da1e-42a5-4957-ae39-129fce907b2c",
 name:"Loja QA",slug:"qa",status:"draft",role:"owner"
};
const draftId="909c803e-63a1-4a47-8c62-bef8727500f7";
async function mockSession(page:Page){
  await page.context().addCookies([{
    name:"csrftoken",value:"qa-only-csrf",url:"http://127.0.0.1:4173",
  }]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:true,
      user:{username:"qa-owner",display_name:"Usuário QA"},tenants:[tenant]})
  }));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,
      items:[],note:"Sem participantes."
    })
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",r=>r.fulfill({
    contentType:"application/json",
    body:JSON.stringify({configured:false,connected:false,store_id:null,
      scope:null,mode:"read_products_only",ready_for_write:false})
  }));
}

for(const width of [390,768,1440]){
  test("Salvar e retomar campanha sem publicação em "+width+"px",async ({page})=>{
    const drafts:Array<Record<string,unknown>>=[];
    await page.setViewportSize({width,height:850});
    await mockSession(page);
    await page.route("**/api/v1/tenants/**/campaign-drafts/",async (route:Route)=>{
      if(route.request().method()==="GET"){
        return route.fulfill({contentType:"application/json",body:JSON.stringify({
          mode:"draft_only",activation_available:false,items:drafts
        })});
      }
      if(route.request().method()==="POST"){
        const input=route.request().postDataJSON();
        const draft={...input,id:draftId,version:1,status:"draft",
          created_at:"2026-11-11T14:00:00Z",updated_at:"2026-11-11T14:00:00Z",
          preview:{credit_per_order_cents:200,max_exposure_cents:20000,
            exceeds_budget:false,assumptions_only:true}};
        drafts.unshift(draft);
        return route.fulfill({status:201,contentType:"application/json",body:JSON.stringify(draft)});
      }
      return route.fulfill({status:405});
    });
    await page.goto("/");
    if(width<=1020) await page.getByRole("button",{name:"Abrir menu"}).click();
    await page.getByRole("button",{name:/^Campanhas/}).click();
    await page.getByRole("button",{name:"Continuar"}).click();
    await page.getByRole("textbox",{name:"Orçamento mensal"}).fill("300,00");
    await page.getByRole("textbox",{name:"Ticket médio estimado"}).fill("100,00");
    await page.getByRole("textbox",{name:"Pedidos pagos estimados"}).fill("100");
    await page.getByRole("button",{name:"Visualizar prévia"}).click();
    await page.getByRole("button",{name:"Salvar rascunho"}).click();
    await expect(page.getByText("Rascunho salvo com segurança.")).toBeVisible();
    await expect(page.getByText("Rascunhos salvos")).toBeVisible();
    await page.getByRole("button",{name:"Novo planejamento"}).last().click();
    await expect(page.getByRole("heading",{name:"Escolha o seu objetivo"})).toBeVisible();
    await page.getByRole("button",{name:/Segunda compra.*300,00/}).click();
    await expect(page.getByRole("heading",{name:"Defina o limite do benefício"})).toBeVisible();
    await expect(page.getByRole("textbox",{name:"Orçamento mensal"})).toHaveValue("300,00");
    await expect(page.getByRole("textbox",{name:"Ticket médio estimado"})).toHaveValue("100,00");
    await expect(page.getByRole("textbox",{name:"Pedidos pagos estimados"})).toHaveValue("100");
    expect(await page.getByRole("button",{name:/Publicar|Ativar campanha/}).count()).toBe(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  });
}
