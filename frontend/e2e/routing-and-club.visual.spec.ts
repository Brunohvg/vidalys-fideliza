import {expect, test, type Page} from "@playwright/test";

const merchant={
  id:"c8a89143-5b6e-4cc6-a599-5bc2d80e2995",
  name:"Loja omnichannel",slug:"loja-omnichannel",status:"active",role:"owner",
};

async function mockMerchant(page:Page){
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      authenticated:true,user:{username:"qa-merchant",display_name:"Pessoa do comércio"},
      tenants:[merchant],
    }),
  }));
}

test("Rotas do lojista suportam deep link, voltar e recarga sem perder a loja",async({page})=>{
  await mockMerchant(page);
  await page.goto("/app/visao-geral");
  await expect(page.getByRole("heading",{name:"O próximo passo da sua loja."})).toBeVisible();
  await page.getByRole("button",{name:"Clientes",exact:true}).click();
  await expect(page).toHaveURL(/\/app\/clientes$/);
  await expect(page.getByRole("heading",{name:"Participantes do clube."})).toBeVisible();
  await page.getByRole("button",{name:"Vendas",exact:true}).click();
  await expect(page).toHaveURL(/\/app\/vendas$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/app\/clientes$/);
  await page.reload();
  await expect(page.getByRole("heading",{name:"Participantes do clube."})).toBeVisible();
  await expect(page.getByLabel("Loja selecionada")).toHaveValue(merchant.id);
});

for(const width of [320,390,768]){
  test("Carteira mobile, VIP, missões e resgate bloqueado em "+width+"px",async({page})=>{
    await page.setViewportSize({width,height:850});
    await page.route("**/api/v1/auth/session/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        authenticated:false,user:null,tenants:[],
      }),
    }));
    const club={
      store_name:"Loja Omnichannel",store_slug:"loja-omnichannel",
      branding:{program_name:"Clube Omnichannel",primary_color:"#087F79",
        accent_color:"#E8F9F4",support_email:"loja@example.invalid"},
      terms:{id:"d87c8583-142d-44c0-88eb-dadead4ac342",version:"v1",
        title:"Termos do clube",body:"Aceite explícito.",
        privacy_notice:"Uso estrito de dados.",approved_at:"2026-11-13T12:00:00Z"},
      signup_available:true,points_enabled:false,rewards_enabled:false,redemption_enabled:false,
    };
    let logged=false;
    await page.route("**/api/v1/public/clubs/loja-omnichannel/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify(club),
    }));
    await page.route("**/api/v1/public/clubs/loja-omnichannel/me/",route=>route.fulfill({
      status:logged?200:401,contentType:"application/json",
      body:JSON.stringify(logged?{
        store_name:club.store_name,display_name:"Cliente Teste",status:"active",
        joined_at:"2026-11-13T12:30:00Z",terms:club.terms,
        points_balance:160,points_pending:30,points_expiring:10,
        points_status:"ledger_only",
        cashback_balance_cents:345,cashback_pending_cents:110,cashback_status:"ledger_only",
        vip_level:"Prata",vip_next_level:"Ouro",vip_progress_percent:45,
        missions:[{id:"profile",title:"Perfil confirmado",state:"eligible"}],
        available_rewards:[],transactions:[],
        redemption_enabled:false,orders_verified:false,note:"Saldo interno sintético",
      }:{detail:"Sem acesso"}),
    }));
    await page.route("**/api/v1/public/clubs/loja-omnichannel/access/confirm/",route=>{
      logged=true;return route.fulfill({contentType:"application/json",
        body:JSON.stringify({authenticated:true})});
    });
    await page.goto("/clube/loja-omnichannel#acesso="+"A".repeat(43));
    await page.getByRole("button",{name:"Confirmar e entrar"}).click();
    const vip=page.getByRole("region",{name:"Meu nível VIP"});
    await expect(vip).toContainText("Prata");
    await expect(vip.getByRole("progressbar",{name:"Progresso para o próximo nível VIP"}))
      .toHaveAttribute("aria-valuenow","45");
    const wallet=page.getByRole("region",{name:"Resumo da minha carteira"});
    await expect(wallet).toContainText("160");
    await expect(wallet).toContainText("R$ 3,45");
    const voucher=page.getByRole("region",{name:"Resgate rápido"});
    await expect(voucher.getByRole("button",{name:"Gerar voucher"})).toBeDisabled();
    await expect(page.getByRole("region",{name:"Missões do clube"})).toContainText("Perfil confirmado");
    await page.getByRole("navigation",{name:"Seu clube"}).getByRole("button",{name:"Histórico"}).click();
    await expect(page).toHaveURL(/\/clube\/loja-omnichannel\/historico$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/clube\/loja-omnichannel$/);
    await expect(page.getByRole("heading",{name:"Recompensas do clube"})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
      .toBeLessThanOrEqual(1);
    await page.goto("/app/visao-geral");
    // Recarregar o shell do lojista nunca herda o token de membro.
    await expect(page.getByRole("heading",{name:"Bem-vindo de volta."})).toBeVisible();
  });
}

test("Rotas desconhecidas não oferecem uma tela autenticada por engano",async({page})=>{
  await mockMerchant(page);
  await page.goto("/app/inexistente");
  await expect(page.getByRole("heading",{name:"Página não encontrada"})).toBeVisible();
  await expect(page.getByRole("navigation",{name:"Seu clube"})).toHaveCount(0);
});
