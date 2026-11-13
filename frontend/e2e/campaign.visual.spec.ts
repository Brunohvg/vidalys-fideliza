import {expect,test} from "@playwright/test";

const tenant={id:"a5ee4147-b23c-4ad2-ae44-c3f5aaf13ed0",
 name:"Loja de teste",slug:"loja-teste",status:"active",role:"owner"};

for(const width of [320,390,768,1440]){
 test("Campanhas de pontos não confundem custo nominal nem estouram "+width+"px",
 async({page},testInfo)=>{
  await page.setViewportSize({width,height:width<=390?844:900});
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({
   contentType:"application/json",body:JSON.stringify({
    authenticated:true,user:{username:"qa",display_name:"QA"},
    tenants:[tenant],
   }),
  }));
  await page.route("**/api/v1/tenants/**/loyalty/point-campaign-drafts/",r=>r.fulfill({
   contentType:"application/json",body:JSON.stringify({
    mode:"draft_only",activation_available:false,items:[],
   }),
  }));
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:/^Campanhas/}).click();
  await expect(page.getByRole("heading",{name:"O que você quer incentivar?"})).toBeVisible();
  await page.getByRole("button",{name:/Reativar clientes/}).click();
  await page.getByRole("button",{name:"Continuar"}).click();
  await page.getByRole("spinbutton",{name:"Pontos extras por pessoa"}).fill("25");
  await page.getByRole("spinbutton",{name:"Número máximo de pessoas"}).fill("100");
  await page.getByRole("button",{name:"Revisar campanha"}).click();
  await expect(page.getByText("2.500 pontos",{exact:false})).toBeVisible();
  await expect(page.getByText("Isso não é um valor em reais",{exact:false})).toHaveCount(0);
  await expect(page.getByText("A campanha não envia e-mail",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:/Publicar campanha|Ativar campanha/})).toHaveCount(0);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  expect(overflow,"viewport "+width).toBeLessThanOrEqual(1);
  await page.screenshot({path:testInfo.outputPath("campaign-points-"+width+".png"),fullPage:true});
 });
}
