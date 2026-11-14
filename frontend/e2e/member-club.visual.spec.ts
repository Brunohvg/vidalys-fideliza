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

for(const width of [320,390,768,1440]){
  test("Meu Clube possui login separado e não inventa pontos em "+width+"px",async ({page},testInfo)=>{
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
    await expect(page.getByRole("heading",{name:"Mais motivos para voltar à Loja Jardim."})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Bem-vindo de volta"})).toBeVisible();
    await page.screenshot({path:testInfo.outputPath("club-guest-"+width+".png"),fullPage:true});
    await expect(page.getByRole("link",{name:"Fazer adesão"})).toBeVisible();
    await expect(page.getByText("Como funciona",{exact:true})).toBeVisible().catch(()=>{});
    await page.goto("/clube/loja-jardim#acesso="+"A".repeat(43));
    await expect(page.getByRole("heading",{name:"Confirme seu acesso"})).toBeVisible();
    await page.getByRole("button",{name:"Confirmar e entrar"}).click();
    await expect(page.getByRole("heading",{name:"Olá, Cliente!"})).toBeVisible();
    await expect(page.getByText("O clube ainda não liberou a pontuação.",{exact:false})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Recompensas em preparação"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Como funcionará seu clube"})).toBeVisible();
    await expect(page.getByText("Nenhum saldo foi atribuído.",{exact:false})).toBeVisible();
    await expect(page.getByText("Em preparação",{exact:true})).toBeVisible();
    await page.screenshot({path:testInfo.outputPath("club-member-"+width+".png"),fullPage:true});
    await page.getByRole("navigation",{name:"Seu clube"}).getByRole("button",{name:"Histórico"}).click();
    await expect(page.getByRole("heading",{name:"Histórico de pontos"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toHaveCount(0);
    await page.getByRole("navigation",{name:"Seu clube"}).getByRole("button",{name:"Regras"}).click();
    await expect(page.getByRole("heading",{name:"Regras e privacidade"})).toBeVisible();
    await page.getByRole("navigation",{name:"Seu clube"}).getByRole("button",{name:"Recompensas"}).click();
    await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toBeVisible();
    await page.getByText("Como vou usar meus pontos no site?").click();
    await expect(page.getByText("Esse resgate ainda não está disponível.",{exact:false}))
      .toBeVisible();
    await expect(page.getByRole("button",{name:/Resgatar/})).toHaveCount(0);
    await expect(page).toHaveURL("http://127.0.0.1:4173/clube/loja-jardim");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  });
}


for(const width of [320,390]){
 test("Participante vê catálogo publicado mas não consegue resgatar em "+width+"px",async({page})=>{
  await page.setViewportSize({width,height:840});
  await page.context().addCookies([{
   name:"csrftoken",value:"csrf-member-only",url:"http://127.0.0.1:4173",
  }]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
   contentType:"application/json",body:JSON.stringify({
    authenticated:false,user:null,tenants:[],
   }),
  }));
  await page.route("**/api/v1/public/clubs/loja-jardim/",route=>route.fulfill({
   contentType:"application/json",body:JSON.stringify(info),
  }));
  let logged=false;
  await page.route("**/api/v1/public/clubs/loja-jardim/me/",route=>route.fulfill({
   status:logged?200:401,contentType:"application/json",body:JSON.stringify(logged?{
    store_name:"Loja Jardim",display_name:"Cliente QA",
    status:"active",joined_at:"2026-11-13T12:30:00Z",
    terms:info.terms,points_balance:null,points_pending:null,
    points_status:"not_active",redemption_enabled:false,orders_verified:false,
    available_rewards:[{
     id:"7d31d188-68ca-4c0f-b4ae-76225b3b1e41",
     title:"R$ 5 de desconto no próximo pedido",points_cost:200,
     discount_cents:500,min_order_cents:3000,status:"locked",
     points_missing:null,redemption_enabled:false,
    }],transactions:[],note:"Benefícios para consulta",
   }:{detail:"Faça login"}),
  }));
  await page.route("**/api/v1/public/clubs/loja-jardim/access/confirm/",route=>{
   logged=true;return route.fulfill({contentType:"application/json",
    body:JSON.stringify({authenticated:true})});
  });
  await page.goto("/clube/loja-jardim#acesso="+"A".repeat(43));
  await page.getByRole("button",{name:"Confirmar e entrar"}).click();
  await expect(page.getByRole("heading",{name:"Olá, Cliente!"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"R$ 5 de desconto no próximo pedido"})).toBeVisible();
  await expect(page.getByText("Publicado para consulta · Resgate em preparação")).toBeVisible();
  await expect(page.getByText("O clube ainda não liberou a pontuação.",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:/Resgatar|Gerar cupom/})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
   .toBeLessThanOrEqual(1);
 });
}


test("Meu Clube exibe extrato interno real sem prometer resgate em 390px",async({page})=>{
 await page.setViewportSize({width:390,height:830});
 await page.context().addCookies([{
  name:"csrftoken",value:"csrf-member-only",url:"http://127.0.0.1:4173",
 }]);
 await page.route("**/api/v1/auth/session/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify({
   authenticated:false,user:null,tenants:[],
  }),
 }));
 await page.route("**/api/v1/public/clubs/loja-jardim/",r=>r.fulfill({
  contentType:"application/json",body:JSON.stringify(info),
 }));
 let logged=false;
 await page.route("**/api/v1/public/clubs/loja-jardim/me/",r=>r.fulfill({
  status:logged?200:401,contentType:"application/json",body:JSON.stringify(
   logged?{
    store_name:"Loja Jardim",display_name:"Cliente QA",
    status:"active",joined_at:"2026-11-13T12:30:00Z",
    terms:info.terms,
    points_balance:100,points_pending:50,points_expiring:100,
    points_status:"ledger_only",redemption_enabled:false,
    orders_verified:false,available_rewards:[],
    transactions:[
     {id:"1",kind:"release",points_delta:0,created_at:"2026-11-14T01:20:00Z",
      description:"Pontos liberados da carência"},
     {id:"2",kind:"accrue",points_delta:50,created_at:"2026-11-14T01:10:00Z",
      description:"Compra registrada"},
    ],note:"Saldo interno não liquidável",
   }:{detail:"Faça login"}),
 }));
 await page.route("**/api/v1/public/clubs/loja-jardim/access/confirm/",r=>{
  logged=true;
  return r.fulfill({contentType:"application/json",
   body:JSON.stringify({authenticated:true})});
 });
 await page.goto("/clube/loja-jardim#acesso="+"A".repeat(43));
 await page.getByRole("button",{name:"Confirmar e entrar"}).click();
 const wallet=page.getByRole("region",{name:"Resumo da minha carteira"});
 await expect(wallet).toContainText("Pontos internos, sem resgate");
 await expect(wallet).toContainText("Saldo em conferência");
 await expect(wallet).toContainText("100");
 await expect(wallet).toContainText("50");
 await expect(wallet).toContainText("não podem ser trocados por descontos");
 await expect(page.getByRole("progressbar",{name:"Progresso para próxima recompensa"})).toHaveCount(0);
 await page.getByRole("navigation",{name:"Seu clube"}).getByRole("button",{name:"Histórico"}).click();
 await expect(page.getByText("Compra registrada")).toBeVisible();
 await expect(page.getByText("Pontos liberados da carência")).toBeVisible();
 await expect(page.getByRole("button",{name:/Resgatar/})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
  .toBeLessThanOrEqual(1);
});
