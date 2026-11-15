import {expect,test} from "@playwright/test";

for(const width of [390,768,1440]){
  test("Apresentação comercial é clara e sem overflow em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:900});
    await page.goto("/");
    await expect(page.getByRole("heading",{level:1,name:/Clientes que voltam/})).toBeVisible();
    await expect(page.getByText("PRÉVIA ILUSTRATIVA · NÃO É SALDO REAL")).toBeVisible();
    await expect(page.getByRole("link",{name:"Conhecer o piloto"})).toHaveAttribute("href","/cadastrar");
    await expect(page.getByRole("navigation",{name:"Apresentação comercial"})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({path:info.outputPath("marketing-home-"+width+".png"),fullPage:true});
    await expect(page.getByRole("link",{name:"Entrar",exact:true}).first()).toHaveAttribute("href","/entrar");
    await page.getByRole("navigation",{name:"Apresentação comercial"}).getByRole("link",{name:"Segmentos"}).click();
    await expect(page).toHaveURL(/\/conhecer\/segmentos$/);
    await expect(page.getByRole("heading",{name:"Artesanato e aviamentos"})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  });
}
test("Catálogo de integrações permite buscar e não anuncia conexão fictícia",async({page},info)=>{
  await page.setViewportSize({width:390,height:860});
  await page.goto("/conhecer/integracoes");
  await expect(page.getByRole("heading",{name:"Nuvemshop"})).toBeVisible();
  await expect(page.getByText("Em homologação",{exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Vidalys Flow"})).toBeVisible();
  await page.getByRole("searchbox",{name:"Buscar integração"}).fill("Nuvemshop");
  await expect(page.getByRole("heading",{name:"Nuvemshop"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Vidalys Flow"})).toHaveCount(0);
  await page.getByRole("searchbox",{name:"Buscar integração"}).fill("XYZ-inexistente");
  await expect(page.getByRole("status")).toContainText("Nenhuma integração encontrada");
  await page.screenshot({path:info.outputPath("marketing-integrations-390.png"),fullPage:true});
});
test("Recursos explicam o que já funciona e o que ainda está planejado",async({page})=>{
  await page.goto("/conhecer/recursos");
  await expect(page.getByRole("heading",{name:"Clube com a marca da sua loja"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Pontos e descontos resgatáveis"})).toBeVisible();
  await expect(page.getByText("Planejado",{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
});
