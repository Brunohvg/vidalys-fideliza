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
async function nav(page:Page,name:string,width:number){
  if(width<=1020) await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.getByRole("button",{name:new RegExp("^"+name)}).click();
}
for(const width of [390,768,1440]) {
  test("Nova experiência: ações, clientes e campanha guiada em "+width+"px",
    async ({page},info)=>{
      await page.setViewportSize({width,height:width===390?844:900});
      await mockMerchant(page);
      await page.goto("/");
      await expect(page.getByRole("heading",{name:"O próximo passo da sua loja."})).toBeVisible();
      await expect(page.getByRole("heading",{name:"Seu plano de ação"})).toBeVisible();
      await expect(page.getByText("Não existem participantes cadastrados nesta loja.")).toBeVisible();
      await expect(page.getByText(/sugestões com IA/i)).toBeVisible();

      await nav(page,"Clientes",width);
      await expect(page.getByRole("heading",{name:"Pessoas no clube",exact:true})).toBeVisible();
      const enrollmentAction=page.getByRole("button",{name:"Gerenciar adesões"});
      await expect(enrollmentAction).toBeVisible();
      const appearance=await enrollmentAction.evaluate(el=>{
        const css=getComputedStyle(el);
        return {radius:css.borderRadius,height:el.getBoundingClientRect().height,display:css.display};
      });
      expect(["flex","inline-flex"]).toContain(appearance.display);
      expect(appearance.radius).not.toBe("0px");
      expect(appearance.height).toBeGreaterThanOrEqual(44);
      await expect(page.getByText("Sua comunidade começa com o primeiro aceite")).toBeVisible();
      await expect(page.getByText("Somente quem confirmou a adesão ao clube aparece aqui.",{exact:false})).toBeVisible();
      expect(await page.getByRole("button",{name:/Cadastrar cliente/}).count()).toBe(0);
      const clientsGeometry=await page.evaluate(()=>({doc:document.documentElement.scrollWidth,width:innerWidth}));
      expect(clientsGeometry.doc).toBeLessThanOrEqual(clientsGeometry.width+1);
      await page.evaluate(()=>window.scrollTo(0,0));
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
      await page.screenshot({path:info.outputPath("new-clients-"+width+".png"),fullPage:true});

      await nav(page,"Campanhas",width);
      await expect(page.getByRole("heading",{name:"O que você quer incentivar?"})).toBeVisible();
      await page.getByRole("button",{name:/Reativar clientes/}).click();
      await page.getByRole("button",{name:"Continuar"}).click();
      await expect(page.getByRole("heading",{name:"Qual benefício você gostaria de oferecer?"})).toBeVisible();
      await page.getByRole("spinbutton",{name:"Pontos extras por pessoa"}).fill("20");
      await page.getByRole("spinbutton",{name:"Número máximo de pessoas"}).fill("100");
      await page.getByRole("button",{name:"Revisar campanha"}).click();
      await expect(page.getByRole("heading",{name:"Sua campanha, antes de publicar"})).toBeVisible();
      await expect(page.getByText("2.000 pontos",{exact:false})).toBeVisible();
      await expect(page.getByText("A campanha não envia e-mail",{exact:false})).toBeVisible();
      const geom=await page.evaluate(()=>({doc:document.documentElement.scrollWidth,width:innerWidth}));
      expect(geom.doc).toBeLessThanOrEqual(geom.width+1);
      await page.evaluate(()=>window.scrollTo(0,0));
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
      await page.screenshot({path:info.outputPath("new-campaign-"+width+".png"),fullPage:true});
      expect(await page.getByRole("button",{name:/Publicar|Ativar/}).count()).toBe(0);
    });
}
test("Ações da loja não fabricam métricas de vendas e encaminham a tarefas",async ({page})=>{
  await mockMerchant(page);
  await page.goto("/");
  await expect(page.getByText("Recomendações baseadas no estado conhecido")).toBeVisible();
  await page.getByRole("button",{name:"Configurar programa"}).click();
  await expect(page.getByRole("heading",{name:"Seu clube em três passos."})).toBeVisible();
});


test("Custo dos benefícios diferencia custo nominal de contribuição estimada",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await mockMerchant(page);
 await page.goto("/");
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
  await page.goto("/");
  await nav(page,"Clientes",width);
  await expect(page.getByRole("heading",{name:"Pessoas no clube"})).toBeVisible();
  const cards=page.locator(".vf-clients-mobile-list");
  const table=page.locator(".xp-table-wrap");
  if(width===390){
   await expect(cards).toBeVisible();
   await expect(table).toBeHidden();
   await expect(cards.locator(".vf-clients-mobile-card")).toHaveCount(1);
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
  await page.goto("/");
  await nav(page,"Resultados",width);
  await expect(page.getByRole("heading",{name:"Seu clube em números que fazem sentido."})).toBeVisible();
  await expect(page.locator(".vf-results-stats article")).toHaveCount(3);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
 });
}
