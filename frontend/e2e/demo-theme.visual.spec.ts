import {expect,test} from "@playwright/test";

// A Demo não consulta a API e nunca representa valores financeiros reais.
for(const width of [390,768,1440]){
  test("Demo v2 usa identidade oficial e continua explícita em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:width===390?844:900});
    await page.goto("/demo");
    await expect(page.getByRole("heading",{name:"Uma experiência de fidelidade que dá vontade de voltar."})).toBeVisible();
    await expect(page.getByText("DADOS FICTÍCIOS")).toBeVisible();
    await expect(page.getByText("DEMO VISUAL V2")).toBeAttached();
    await expect(page.getByRole("link",{name:"Ver site oficial"})).toHaveAttribute("href","/");
    await expect(page.locator(".layout .sidebar")).toHaveCSS("background-color","rgb(16, 37, 62)");
    await expect(page.locator(".layout .button-primary").first())
      .toHaveCSS("background-color","rgb(8, 127, 121)");
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({path:info.outputPath("demo-v2-"+width+".png"),fullPage:true});
    if(width<=980)await page.getByRole("button",{name:"Abrir menu"}).click();
    await page.getByRole("navigation",{name:"Seções"}).getByRole("button",{name:"Programa"}).click();
    await expect(page.getByRole("heading",{name:"Desconto na próxima compra"})).toBeVisible();
    await expect(page.getByText("Cashback promocional")).toHaveCount(0);
  });
}
test("Demo v2 mostra apenas pontos fictícios e explica limites",async({page})=>{
  await page.goto("/demo");
  await page.getByRole("navigation",{name:"Seções"}).getByRole("button",{name:"Meu Clube"}).click();
  await expect(page.getByText("Pontos do exemplo")).toBeVisible();
  await expect(page.getByText("Saldo demonstrativo")).toBeVisible();
  await page.getByRole("button",{name:"Sobre a demonstração"}).click();
  await expect(page.getByRole("dialog")).toContainText("Todos os números e clientes desta página são fictícios");
});
