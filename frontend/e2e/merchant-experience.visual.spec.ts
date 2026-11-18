import {expect, test, type Page} from "@playwright/test";

const tenant={
  id:"11ada079-bb53-409a-b321-8866423fdba0",
  name:"Loja demonstração",slug:"demo-merchant",
  status:"draft",role:"owner"
};
async function mockMerchant(page:Page) {
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:true,
      user:{username:"qa-merchant",display_name:"Lojista QA"},tenants:[tenant]})
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:0,active:0,paused:0},total_filtered:0,
      limit:20,offset:0,items:[],note:"Ainda não há adesões."
    })
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({configured:false,connected:false,store_id:null,scope:null,
      mode:"read_products_only",ready_for_write:false})
  }));
}
const toolPaths:Record<string,string>={"Custo dos benefícios":"/app/ferramentas/margem",
  "Custos dos produtos":"/app/ferramentas/custos","Conciliação":"/app/ferramentas/conciliacao"};
async function nav(page:Page,name:string,width:number){
  if(toolPaths[name]){await page.goto(toolPaths[name]);return;}
  if(width<=1020) await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator("#portal-sidebar").getByRole("button",{name:new RegExp("^"+name)}).click();
}
for(const width of [390,768,1440]) {
  test("Nova experiência: ações, clientes e campanha guiada em "+width+"px",
    async ({page},info)=>{
      await page.setViewportSize({width,height:width===390?844:900});
      await mockMerchant(page);
      await page.goto("/app/visao-geral");
      await expect(page.getByRole("heading",{name:"Seu clube hoje"})).toBeVisible();
      await expect(page.getByRole("heading",{name:"O que fazer agora"})).toBeVisible();
      await expect(page.getByRole("region",{name:"Indicadores reais do clube"})).toContainText("Participantes");
      await expect(page.getByRole("heading",{name:"PRÓXIMA AÇÃO RECOMENDADA"})).toHaveCount(0);

      await nav(page,"Clientes",width);
      await expect(page.getByRole("heading",{name:"Quem faz parte do clube",exact:true})).toBeVisible();
      const enrollmentAction=page.getByRole("button",{name:"Gerenciar adesões"});
      await expect(enrollmentAction).toBeVisible();
      const appearance=await enrollmentAction.evaluate(el=>{
        const css=getComputedStyle(el);
        return {radius:css.borderRadius,height:el.getBoundingClientRect().height,display:css.display};
      });
      expect(["flex","inline-flex"]).toContain(appearance.display);
      expect(appearance.radius).not.toBe("0px");
      expect(appearance.height).toBeGreaterThanOrEqual(44);
      await expect(page.getByText("Seu clube começa com o primeiro cliente")).toBeVisible();
      await expect(page.getByText("Só entra quem aceita o regulamento.",{exact:false})).toBeVisible();
      expect(await page.getByRole("button",{name:/Cadastrar cliente/}).count()).toBe(0);
      const clientsGeometry=await page.evaluate(()=>({doc:document.documentElement.scrollWidth,width:innerWidth}));
      expect(clientsGeometry.doc).toBeLessThanOrEqual(clientsGeometry.width+1);
      await page.evaluate(()=>window.scrollTo(0,0));
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
      await page.screenshot({path:info.outputPath("new-clients-"+width+".png"),fullPage:true});

      await nav(page,"Campanhas",width);
      await page.getByRole("button",{name:"Nova campanha"}).click();
      await expect(page.getByRole("heading",{name:"Qual é o objetivo?"})).toBeVisible();
      await page.getByRole("button",{name:/Trazer de volta/}).click();
      await expect(page.getByRole("heading",{name:"Quanto de bônus?"})).toBeVisible();
      await page.getByRole("spinbutton",{name:"Pontos extras por pessoa"}).fill("20");
      await page.getByRole("spinbutton",{name:"Número máximo de pessoas"}).fill("100");
      await page.getByRole("button",{name:"Próximo"}).click();
      await page.getByRole("button",{name:"Próximo"}).click();
      await expect(page.getByRole("heading",{name:"Revise antes de publicar"})).toBeVisible();
      await expect(page.getByText("20 pontos extras por pessoa",{exact:false})).toBeVisible();
      await expect(page.getByText("Nenhum ponto é creditado e nada é enviado",{exact:false})).toBeVisible();
      const geom=await page.evaluate(()=>({doc:document.documentElement.scrollWidth,width:innerWidth}));
      expect(geom.doc).toBeLessThanOrEqual(geom.width+1);
      await page.evaluate(()=>window.scrollTo(0,0));
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
      await page.screenshot({path:info.outputPath("new-campaign-"+width+".png"),fullPage:true});
      expect(await page.getByRole("button",{name:/Ativar/}).count()).toBe(0);
    });
}
test("Ações da loja não fabricam métricas de vendas e encaminham a tarefas",async ({page})=>{
  await mockMerchant(page);
  await page.goto("/app/visao-geral");
  await expect(page.getByRole("region",{name:"Indicadores reais do clube"})).toBeVisible();
  await page.getByRole("button",{name:/Recompensas publicadas/}).click();
  await expect(page.getByRole("tab",{name:"2. Como usar"})).toHaveAttribute("aria-selected","true");
});


test("Custo dos benefícios diferencia custo nominal de contribuição estimada",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await mockMerchant(page);
 await page.goto("/app/visao-geral");
 await nav(page,"Custo dos benefícios",390);
 await expect(page.getByRole("heading",{name:"Quanto pode custar uma recompensa?"})).toBeVisible();
 await page.getByRole("textbox",{name:"Valor da próxima compra"}).fill("100,00");
 await page.getByRole("textbox",{name:"Desconto por recompensa"}).fill("5,00");
 await expect(page.getByText("R$ 50,00",{exact:false})).toBeVisible();
 await page.getByRole("button",{name:"Ver impacto na margem (opcional)"}).click();
 // Nenhum custo deve ser presumido; o lojista precisa informar a cesta completa.
 await expect(page.getByRole("textbox",{name:"Custo total dos produtos"})).toHaveValue("");
 await expect(page.getByRole("textbox",{name:"Taxas e impostos"})).toHaveValue("");
 await expect(page.getByText("Contribuição indisponível:",{exact:false})).toBeVisible();
 await page.getByRole("textbox",{name:"Custo total dos produtos"}).fill("60,00");
 await page.getByRole("textbox",{name:"Taxas e impostos"}).fill("10,00");
 await page.getByRole("textbox",{name:"Frete subsidiado pela loja"}).fill("5,00");
 await page.getByRole("textbox",{name:"Outras despesas variáveis"}).fill("0,00");
 await expect(page.getByText("Contribuição estimada após desconto:",{exact:false})).toBeVisible();
 await expect(page.getByText("R$ 20,00",{exact:true})).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
 expect(overflow).toBeLessThanOrEqual(1);
});


for(const width of [390,1440]){
 test("Diretório de participantes exibe somente um layout em "+width+"px",async({page})=>{
  await page.setViewportSize({width,height:900});
  await mockMerchant(page);
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
   contentType:"application/json",body:JSON.stringify({
    source:"verified_opt_in_only",data_status:"consent_verified",
    summary:{total:1,active:1,paused:0},total_filtered:1,limit:20,offset:0,
    items:[{id:"decd72f1-3dde-4254-aea2-041a39fa3e80",display_name:"Participante Exemplo",
      contact_email:"exemplo@example.invalid",status:"active",
      consented_at:"2026-11-13T15:00:00-03:00",consent_channel:"customer_portal",
      last_program_activity_at:null,balance_status:"unavailable",cashback_balance_cents:null}],
   }),
  }));
  await page.goto("/app/visao-geral");
  await nav(page,"Clientes",width);
  await expect(page.getByRole("heading",{name:"Quem faz parte do clube"})).toBeVisible();
  const cards=page.locator(".vf-clients-cards");
  const table=page.locator(".vf-clients-table");
  if(width===390){
   await expect(cards).toBeVisible();
   await expect(table).toBeHidden();
   await expect(cards.locator("li")).toHaveCount(1);
  }else{
   await expect(cards).toBeHidden();
   await expect(table).toBeVisible();
   await expect(table.locator("tbody tr")).toHaveCount(1);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
 });
}


for(const width of [390,1440]){
 test("Resultados permanece legível e sem rolagem horizontal em "+width+"px",async({page})=>{
  await page.setViewportSize({width,height:900});
  await mockMerchant(page);
  await page.route("**/api/v1/tenants/**/sales/manual/",route=>route.fulfill({
   contentType:"application/json",body:JSON.stringify({items:[],count:0,total:0}),
  }));
  await page.goto("/app/visao-geral");
  await nav(page,"Resultados",width);
  await expect(page.getByRole("heading",{name:"O que o clube trouxe"})).toBeVisible();
  await expect(page.locator(".vf-res-kpi")).toHaveCount(3);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
 });
}
