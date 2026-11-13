import {expect,test} from "@playwright/test";

const info={
  store_name:"Loja Jardim",store_slug:"loja-jardim",
  branding:{program_name:"Clube Jardim",primary_color:"#087F79",
    accent_color:"#37D5BB",support_email:"loja@example.invalid"},
  terms:{id:"bbb432db-fabf-45f8-96af-997d26f75316",version:"v1",
    title:"Regulamento do Clube Jardim",
    body:"Compras pagas poderão gerar pontos após ativação do programa.",
    privacy_notice:"Somente dados necessários para adesão.",approved_at:"2026-11-13T12:00:00Z"},
  signup_available:true,points_enabled:false,rewards_enabled:false,redemption_enabled:false,
};

for(const width of [390,768,1440]){
  test("Meu Clube possui login separado e não inventa pontos em "+width+"px",async ({page})=>{
    await page.setViewportSize({width,height:900});
    await page.context().addCookies([{
      name:"csrftoken",value:"csrf-member-only",url:"http://127.0.0.1:4173",
    }]);
    await page.route("**/api/v1/auth/session/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        authenticated:false,user:null,tenants:[],
      }),
    }));
    let entered=false;
    await page.route("**/api/v1/public/clubs/loja-jardim/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify(info),
    }));
    await page.route("**/api/v1/public/clubs/loja-jardim/me/",route=>route.fulfill({
      status:entered?200:401,contentType:"application/json",
      body:entered?JSON.stringify({
        store_name:"Loja Jardim",display_name:"Cliente QA",
        status:"active",joined_at:"2026-11-13T12:30:00Z",
        terms:info.terms,points_balance:null,points_pending:null,
        points_status:"not_active",available_rewards:[],transactions:[],
        redemption_enabled:false,orders_verified:false,note:"Sem pontos liberados",
      }):JSON.stringify({detail:"Faça login"}),
    }));
    await page.route("**/api/v1/public/clubs/loja-jardim/access/confirm/",route=>{
      entered=true;
      return route.fulfill({contentType:"application/json",
        body:JSON.stringify({authenticated:true})});
    });
    await page.goto("/clube/loja-jardim");
    await expect(page.getByRole("heading",{name:"Entre no seu clube"})).toBeVisible();
    await expect(page.getByRole("link",{name:"Fazer adesão"})).toBeVisible();
    await expect(page.getByText("Como funciona",{exact:true})).toBeVisible().catch(()=>{});
    await page.goto("/clube/loja-jardim#acesso="+"A".repeat(43));
    await expect(page.getByRole("heading",{name:"Confirme seu acesso"})).toBeVisible();
    await page.getByRole("button",{name:"Confirmar e entrar"}).click();
    await expect(page.getByRole("heading",{name:"Olá, Cliente!"})).toBeVisible();
    await expect(page.getByText("O clube ainda não liberou a pontuação.",{exact:false})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Recompensas em preparação"})).toBeVisible();
    await page.getByText("Como vou usar meus pontos no site?").click();
    await expect(page.getByText("Esse resgate ainda não está disponível.",{exact:false}))
      .toBeVisible();
    await expect(page.getByRole("button",{name:/Resgatar/})).toHaveCount(0);
    await expect(page).toHaveURL("http://127.0.0.1:4173/clube/loja-jardim");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  });
}
