import {expect, test, type Page} from "@playwright/test";

const tenant = {
  id:"b01159fb-2f05-4b42-bb29-0d831a009847",
  name:"Loja QA",slug:"loja-qa",status:"draft",role:"owner"
};

async function loginMock(page:Page) {
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:true,user:{username:"qa",display_name:"Usuário QA"},tenants:[tenant]})
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:0,active:0,paused:0},total_filtered:0,
      limit:20,offset:0,items:[],note:"Nenhum participante."
    })
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:false,connected:false,store_id:null,scope:null,
      mode:"read_products_only",ready_for_write:false
    })
  }));
}

for (const width of [390, 768, 1440]) {
  test("Menu acessível em viewport baixa: "+width+"x700",async ({page})=>{
    await page.setViewportSize({width,height:700});
    await loginMock(page);
    await page.goto("/");
    if(width<=1020) await page.getByRole("button",{name:"Abrir menu"}).click();

    const menu=page.getByRole("complementary",{name:"Menu do lojista"});
    await expect(menu.getByRole("button",{name:"Visão geral"})).toBeVisible();
    await expect(menu.getByRole("button",{name:"Clientes"})).toBeVisible();
    await expect(menu.getByText("Mais ferramentas")).toBeVisible();
    await menu.locator(".portal-advanced-menu > summary").click();
    await expect(menu.getByRole("button",{name:/Campanhas/})).toBeVisible();
    await expect(menu.getByRole("button",{name:/Sair da conta/})).toBeAttached();
    await menu.getByRole("button",{name:"Clientes"}).click();
    await expect(page.getByRole("heading",{name:"Pessoas no clube",exact:true})).toBeVisible();
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
      .toBeLessThanOrEqual(1);
  });
}
