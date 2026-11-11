import {expect, test, type Page} from "@playwright/test";

const store={
  id:"264c8396-604b-4cfb-bfa4-0ba8bb27be58",
  name:"Loja laboratório",slug:"loja-lab",
  role:"owner",status:"draft"
};

async function mockShop(page: Page) {
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:true,user:{username:"lab",display_name:"Lojista teste"},
      tenants:[store]})
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,
      items:[],note:"Sem participantes"})
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({configured:false,connected:false,store_id:null,
      scope:null,mode:"read_products_only",ready_for_write:false})
  }));
}

for (const width of [390,768,1440]){
  test("Identidade de fidelização, responsividade e prévia do benefício em "+width+"px",
    async ({page},info)=>{
      await page.setViewportSize({width,height:width===390?844:900});
      await mockShop(page);
      await page.goto("/");
      await expect(page.getByRole("heading",{name:"Seu plano de ação"})).toBeVisible();
      const palette=await page.evaluate(()=>{
        const root=getComputedStyle(document.documentElement);
        const cta=document.querySelector(".portal-primary");
        return {
          primary:root.getPropertyValue("--vf-primary").trim(),
          mint:root.getPropertyValue("--vf-mint").trim(),
          gold:root.getPropertyValue("--vf-reward").trim(),
          navy:root.getPropertyValue("--vf-ink").trim(),
          overflow:document.documentElement.scrollWidth-innerWidth,
          displayFont:getComputedStyle(document.querySelector(".xp-action-banner h2")!).fontFamily,
          mainArea:document.querySelector(".portal-main")?.getBoundingClientRect().left
        };
      });
      expect(palette.primary).toBe("#087F79");
      expect(palette.mint).toBe("#37D5BB");
      expect(palette.gold).toBe("#F5BA51");
      expect(palette.navy).toBe("#10253E");
      expect(palette.displayFont).toContain("Manrope");
      expect(palette.overflow).toBeLessThanOrEqual(1);
      if(width<=1020) expect(palette.mainArea).toBeLessThanOrEqual(1);
      await page.evaluate(()=>scrollTo(0,0));
      await page.screenshot({
        path:info.outputPath("loyalty-dashboard-"+width+".png"),fullPage:true
      });

      if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
      await page.locator(".portal-nav").getByRole("button",{name:/^Campanhas/}).click();
      await expect(page.getByRole("heading",{name:"Escolha o seu objetivo"})).toBeVisible();
      await page.getByRole("button",{name:"Continuar"}).click();
      await page.getByRole("textbox",{name:"Orçamento mensal"}).fill("300,00");
      await page.getByRole("textbox",{name:"Ticket médio estimado"}).fill("100,00");
      await page.getByRole("textbox",{name:"Pedidos pagos estimados"}).fill("50");
      await page.getByRole("button",{name:"Visualizar prévia"}).click();
      await expect(page.getByRole("heading",{name:"Sua campanha, antes de começar"})).toBeVisible();
      const wallet=page.getByRole("complementary",{name:"Prévia ilustrativa da recompensa"});
      await expect(wallet).toBeVisible();
      await expect(wallet.getByText("R$ 2,00",{exact:true})).toBeVisible();
      await expect(wallet.getByText(/Não disponível para uso/)).toBeVisible();
      await expect(page.getByText("Ativação indisponível:")).toBeVisible();
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      await page.evaluate(()=>scrollTo(0,0));
      await page.screenshot({
        path:info.outputPath("loyalty-reward-preview-"+width+".png"),fullPage:true
      });
    });
}

test("Login usa identidade nova sem afirmar programa ativo",async ({page})=>{
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:false,user:null,tenants:[]})
  }));
  await page.goto("/");
  await expect(page.getByText("Mais conexão.")).toBeVisible();
  await expect(page.getByText("Mais motivos para voltar.")).toBeVisible();
  const hero=page.locator(".portal-auth-brand");
  await expect(hero).toBeVisible();
  const colors=await hero.evaluate(el=>({
    background:getComputedStyle(el).backgroundImage,
    title:getComputedStyle(el.querySelector("h1")!).fontFamily
  }));
  expect(colors.background).toContain("rgb(16, 37, 62)");
  expect(colors.title).toContain("Manrope");
});
