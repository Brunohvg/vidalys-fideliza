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
      await expect(page.getByRole("heading",{name:"Participantes",exact:true})).toBeVisible();
      await expect(page.getByText("Sua comunidade começa com o primeiro aceite")).toBeVisible();
      await expect(page.getByText("Não ativados")).toBeVisible();
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
  await expect(page.getByRole("heading",{name:"Um programa simples para a loja. Claro para o cliente."})).toBeVisible();
});
