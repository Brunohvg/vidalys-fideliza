import {expect,test,type Page} from "@playwright/test";

const store={
 id:"e483dc55-7434-44a5-8376-45f70b6c7ae4",
 name:"Loja de Teste do Clube",slug:"loja-clube-qa",
 status:"active",role:"owner",
};
async function setup(page:Page){
  await page.context().addCookies([{
    name:"csrftoken",value:"trial-csrf-test",url:"http://127.0.0.1:4173",
  }]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      authenticated:true,user:{username:"pilot-owner",display_name:"Lojista Piloto"},
      tenants:[store],
    }),
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"consent_verified",
      summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,
      items:[],note:"Sem adesões",
    }),
  }));
  await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",route=>{
    expect(route.request().method()).toBe("GET");
    return route.fulfill({contentType:"application/json",body:JSON.stringify({
      mode:"draft_only",activation_available:false,
      rule:{version:1,points:1,per_cents:100,hold_days:7,validity_days:180},
    })});
  });
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",route=>{
    expect(route.request().method()).toBe("GET");
    return route.fulfill({contentType:"application/json",body:JSON.stringify({
      mode:"draft_only",activation_available:false,
      items:[{
        id:"4f44ab02-f690-4e8d-86a8-23edc454ff65",
        title:"R$ 5 na próxima compra",points_cost:200,
        discount_cents:500,min_order_cents:3000,max_redemptions:25,
        status:"draft",published:false,redemption_enabled:false,
      }],
    })});
  });
}
for(const width of [320,390,1440]){
  test("Laboratório da jornada sem crédito e com estados distintos em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:860});
    await setup(page);
    const writes:string[]=[];
    page.on("request",request=>{
      if(request.url().includes("/api/v1/")&&
        !["GET","HEAD","OPTIONS"].includes(request.method()))writes.push(request.url());
    });
    await page.goto("/");
    if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
    await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
      await page.getByRole("navigation",{name:"Áreas do programa"}).getByRole("button",{name:"Testes"}).click();
    await page.getByText("Testar pontos e recompensas sem publicar").click();
    await expect(page.getByRole("heading",{name:"Teste o caminho dos pontos"})).toBeVisible();
    const result=page.getByRole("region",{name:"Resultado da simulação"});
    await expect(result).toContainText("Os pontos ficam pendentes");
    await expect(result.locator(".vf-trial-result-grid>div").nth(0).locator("strong"))
      .toHaveText("200");
    await expect(result.locator(".vf-trial-result-grid>div").nth(1).locator("strong"))
      .toHaveText("200");
    await expect(result.locator(".vf-trial-result-grid>div").nth(2).locator("strong"))
      .toHaveText("0");
    await page.getByRole("button",{name:"Pontos liberados"}).click();
    await expect(result).toContainText("a recompensa poderia ser resgatada");
    await expect(result).toContainText("R$ 5,00");
    await expect(result).toContainText("Saldo teórico após a troca: 0 pontos");
    await page.getByRole("textbox",{name:"Próxima compra no checkout (R$)"}).fill("20,00");
    await expect(result).toContainText("abaixo do mínimo da recompensa");
    await page.getByRole("textbox",{name:"Próxima compra no checkout (R$)"}).fill("50,00");
    await page.getByRole("button",{name:"Cancelamento"}).click();
    await expect(result).toContainText("Pedido cancelado ou estornado");
    await expect(result.locator(".vf-trial-result-grid>div").nth(3).locator("strong"))
      .toHaveText("R$ 0,00");
    await page.getByRole("button",{name:"Aguardando pagamento"}).click();
    await expect(result).toContainText("Pagamento pendente");
    await page.getByRole("button",{name:"Pontos vencidos"}).click();
    await expect(result).toContainText("Pontos vencidos");
    await page.getByRole("textbox",{name:"Compra elegível de teste (R$)"}).fill("valor inválido");
    await expect(result).toContainText("Preencha valores válidos");
    await expect(page.getByText("nenhum cupom será criado",{exact:false})).toBeVisible();
    expect(writes,"laboratório não pode postar dados ao backend").toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
      .toBeLessThanOrEqual(1);
    await page.screenshot({
      path:info.outputPath("loyalty-trial-"+width+".png"),fullPage:true,
    });
  });
}
