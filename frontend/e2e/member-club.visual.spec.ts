import {expect,test,type Page} from "@playwright/test";

/* Meu Clube — página única do cliente (/clube/<loja>) pelo protótipo aprovado.
   Visitante participa ou entra por link; cliente vê saldo, trocas, extrato e regras.
   Nunca mostra saldo inventado: sem dado verificado aparece "—". */

const terms={id:"bbb432db-fabf-45f8-96af-997d26f75316",version:"v1",
  title:"Regulamento do Clube Jardim",
  body:"Compras pagas poderão gerar pontos após ativação do programa.",
  privacy_notice:"Somente dados necessários para adesão.",approved_at:"2026-11-13T12:00:00Z"};
const reward={id:"7d31d188-68ca-4c0f-b4ae-76225b3b1e41",title:"R$ 5 de desconto no próximo pedido",
  points_cost:200,discount_cents:500,min_order_cents:3000,redemption_unit:"points",
  status:"locked",points_missing:null,redemption_enabled:false};
const info={
  store_name:"Loja Jardim",store_slug:"loja-jardim",
  branding:{program_name:"Clube Jardim",primary_color:"#0B4FA8",
    accent_color:"#FF8A3D",support_email:"loja@example.invalid"},
  terms,signup_available:true,points_enabled:false,rewards_enabled:false,redemption_enabled:false,
  published_rewards:[reward],earning:{points:2,per_cents:100,hold_days:7,validity_days:365},
};
const member={
  store_name:"Loja Jardim",display_name:"Cliente QA",phone_last4:"8888",
  status:"active",joined_at:"2026-11-13T12:30:00Z",terms,
  points_balance:null,points_pending:null,points_expiring:null,points_status:"not_active",
  available_rewards:[reward],transactions:[],redemption_enabled:false,orders_verified:false,note:"",
};

async function mockClub(page:Page,opts:{club?:object;me?:object;loggedIn?:boolean}={}){
  await page.context().addCookies([{name:"csrftoken",value:"csrf-member-only",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify({authenticated:false,user:null,tenants:[]})}));
  let logged=Boolean(opts.loggedIn);
  await page.route("**/api/v1/public/clubs/*/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify(opts.club??info)}));
  await page.route("**/api/v1/public/clubs/*/me/",r=>r.fulfill({status:logged?200:401,contentType:"application/json",
    body:JSON.stringify(logged?(opts.me??member):{detail:"Faça login"})}));
  await page.route("**/api/v1/public/clubs/*/access/confirm/",r=>{logged=true;
    return r.fulfill({contentType:"application/json",body:JSON.stringify({authenticated:true})});});
  await page.route("**/api/v1/public/clubs/*/access/request/",r=>r.fulfill({status:202,contentType:"application/json",
    body:JSON.stringify({status:"accepted"})}));
  await page.route("**/api/v1/public/clubs/*/logout/",r=>{logged=false;
    return r.fulfill({contentType:"application/json",body:JSON.stringify({authenticated:false})});});
}
const noOverflow=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);

for(const width of [320,390,768,1440]){
  test("Visitante entende a regra, participa e entra pelo link em "+width+"px",async({page},testInfo)=>{
    await page.setViewportSize({width,height:900});
    await mockClub(page);
    let joined:Record<string,unknown>|null=null;
    await page.route("**/api/v1/public/programs/loja-jardim/join/",r=>{joined=r.request().postDataJSON();
      return r.fulfill({status:202,contentType:"application/json",body:JSON.stringify({status:"pending_verification",
        participant_created:false,cashback_enabled:false,terms_version:"v1",message:"ok"})});});
    await page.goto("/clube/loja-jardim");
    await expect(page.getByRole("heading",{name:"Ganhe 2% de volta em toda compra."})).toBeVisible();
    await expect(page.getByText("A cada R$ 1,00 em compras, você ganha 2 pontos.",{exact:false})).toBeVisible();
    await expect(page.getByText("Com 200 pontos",{exact:false})).toBeVisible();
    await expect(page.getByText("os pontos começam a contar quando ela ativar",{exact:false})).toBeVisible();
    await expect(page.getByRole("heading",{name:"O que dá para trocar"})).toBeVisible();
    await expect(page.locator(".clb-hero")).toHaveCSS("background-image",/linear-gradient/);
    await noOverflow(page);
    await page.screenshot({path:testInfo.outputPath("club-guest-"+width+".png"),fullPage:true});

    const submit=page.getByRole("button",{name:"Entrar no clube"});
    await expect(submit).toBeDisabled();
    await page.getByRole("textbox",{name:"Seu nome"}).fill("Cliente Interessada");
    await page.getByRole("textbox",{name:"E-mail"}).fill("cliente@example.invalid");
    await page.getByRole("textbox",{name:/Celular/}).fill("(31) 99999-8888");
    await page.getByRole("checkbox",{name:/Li e aceito o regulamento/}).check();
    await expect(page.getByRole("checkbox",{name:/ofertas da loja/})).not.toBeChecked();
    await submit.click();
    await expect(page.getByRole("heading",{name:"Confira seu e-mail"})).toBeVisible();
    expect(joined).toMatchObject({name:"Cliente Interessada",email:"cliente@example.invalid",
      phone:"(31) 99999-8888",terms_version:"v1",accepted_terms:true,marketing_opt_in:false});

    await page.goto("/clube/loja-jardim#acesso="+"A".repeat(43));
    await expect(page.getByRole("heading",{name:"Confirme seu acesso"})).toBeVisible();
    await page.getByRole("button",{name:"Confirmar e entrar"}).click();
    await expect(page.getByText("Olá, Cliente")).toBeVisible();
    const wallet=page.getByRole("region",{name:"Seu saldo"});
    await expect(wallet).toContainText("—");
    await expect(wallet).toContainText("A loja ainda não ativou a pontuação");
    await noOverflow(page);
    await page.screenshot({path:testInfo.outputPath("club-member-"+width+".png"),fullPage:true});
  });
}

test("Quem já participa entra com o código do e-mail e fica conectado",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});
  await mockClub(page);
  let sent:Record<string,unknown>|null=null;
  await page.route("**/api/v1/public/clubs/*/access/code/",async r=>{sent=r.request().postDataJSON();
    await page.unroute("**/api/v1/public/clubs/*/me/");
    await page.route("**/api/v1/public/clubs/*/me/",m=>m.fulfill({contentType:"application/json",body:JSON.stringify(member)}));
    return r.fulfill({contentType:"application/json",body:JSON.stringify({authenticated:true,remembered:true})});});
  await page.goto("/clube/loja-jardim");
  await page.getByRole("button",{name:"Entrar",exact:true}).click();
  await page.getByRole("textbox",{name:"Seu e-mail"}).fill("cliente@example.invalid");
  await page.getByRole("button",{name:"Receber código de acesso"}).click();
  await expect(page.getByRole("heading",{name:"Digite o código do e-mail"})).toBeVisible();
  await expect(page.getByText("Se cliente@example.invalid participa do clube",{exact:false})).toBeVisible();
  const enter=page.getByRole("button",{name:"Entrar",exact:true});
  await expect(enter).toBeDisabled();
  await page.getByRole("textbox",{name:"Código"}).fill("123 456");
  await expect(page.getByRole("checkbox",{name:/Manter conectado/})).toBeChecked();
  await page.screenshot({path:testInfo.outputPath("club-code-390.png"),fullPage:true});
  await enter.click();
  await expect(page.getByText("Olá, Cliente")).toBeVisible();
  expect(sent).toEqual({email:"cliente@example.invalid",code:"123456",remember:true});
});

test("Link antigo de adesão abre o clube no formulário",async({page})=>{
  await mockClub(page);
  await page.goto("/participar/loja-jardim");
  await expect(page).toHaveURL(/\/clube\/loja-jardim#participar$/);
  await expect(page.getByRole("heading",{name:"Quero participar"})).toBeVisible();
});

test("Endereço antigo mostra o endereço novo da loja",async({page})=>{
  await mockClub(page);
  await page.goto("/clube/loja-jardim-3f9a2b1c4d5e");
  await expect(page).toHaveURL(/\/clube\/loja-jardim$/);
  await expect(page.getByRole("heading",{name:"Ganhe 2% de volta em toda compra."})).toBeVisible();
});

for(const width of [390,1440]){
  test("Cliente com saldo vê troca, extrato, regras e mostra no caixa em "+width+"px",async({page},testInfo)=>{
    await page.setViewportSize({width,height:900});
    const ready={...reward,id:"a1",title:"R$ 5 de desconto",status:"available",redemption_enabled:true};
    const far={...reward,id:"a2",title:"R$ 15 de desconto",points_cost:1500,discount_cents:1500,min_order_cents:0};
    await mockClub(page,{loggedIn:true,me:{...member,points_balance:1240,points_pending:180,points_expiring:120,
      points_status:"verified",redemption_enabled:true,available_rewards:[ready,far],
      transactions:[{id:"t1",kind:"accrue",points_delta:128,created_at:"2026-11-14T10:00:00Z",description:"Compra na loja"},
        {id:"t2",kind:"redeem",points_delta:-500,created_at:"2026-11-02T10:00:00Z",description:"Troca: R$ 5 de desconto"}]}});
    let issued=false;
    await page.route("**/api/v1/public/clubs/loja-jardim/vouchers/issue/",r=>{issued=true;
      return r.fulfill({contentType:"application/json",body:JSON.stringify({code:"ANA-5K2Q",voucher_id:"v1",
        discount_cents:500,expires_at:"2026-12-18T00:00:00Z",external_coupon_created:false})});});
    await page.goto("/clube/loja-jardim");
    const wallet=page.getByRole("region",{name:"Seu saldo"});
    await expect(wallet).toContainText("1.240");
    await expect(wallet).toContainText("R$ 12,40");
    await expect(page.getByText("120 pontos vencem em breve")).toBeVisible();
    await expect(page.getByRole("heading",{name:"Próxima troca"})).toBeVisible();
    await expect(page.getByText("faltam 260 pontos")).toBeVisible();
    await page.getByRole("button",{name:"Mostrar no caixa"}).click();
    const sheet=page.getByRole("dialog",{name:"Mostre ao vendedor"});
    await expect(sheet).toContainText("Celular final 8888");
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await noOverflow(page);
    await page.screenshot({path:testInfo.outputPath("club-home-"+width+".png"),fullPage:true});

    const tabs=page.getByRole("navigation",{name:"Seções do clube"});
    await tabs.getByRole("button",{name:"Trocar"}).click();
    await expect(page).toHaveURL(/\/clube\/loja-jardim\/recompensas$/);
    await expect(page.getByText("faltam 260")).toBeVisible();
    await page.getByRole("main").getByRole("button",{name:"Trocar",exact:true}).click();
    await expect(page.getByText("ANA-5K2Q")).toBeVisible();
    expect(issued).toBe(true);
    await tabs.getByRole("button",{name:"Extrato"}).click();
    await expect(page).toHaveURL(/\/historico$/);
    await expect(page.getByText("Compra na loja")).toBeVisible();
    await expect(page.getByText("+128")).toBeVisible();
    await tabs.getByRole("button",{name:"Regras"}).click();
    await expect(page.getByText("Pontos liberam em 7 dias.")).toBeVisible();
    await expect(page.getByText("Valem 365 dias.")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/historico$/);
    await noOverflow(page);
  });
}

test("Trocas fechadas não oferecem botão e o saldo em conferência é avisado",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await mockClub(page,{loggedIn:true,me:{...member,points_balance:100,points_status:"ledger_only"}});
  await page.goto("/clube/loja-jardim/recompensas");
  await expect(page.getByText("Trocas ainda não abertas")).toBeVisible();
  await expect(page.getByRole("main").getByRole("button",{name:"Trocar",exact:true})).toHaveCount(0);
  await expect(page.getByText("faltam 100")).toBeVisible();
  await page.getByRole("navigation",{name:"Seções do clube"}).getByRole("button",{name:"Início"}).click();
  await expect(page.getByText("Saldo em conferência",{exact:false})).toBeVisible();
});

for(const width of [390,1440]){
  test("Perfil: completa dados, ofertas por e-mail, app e saída em "+width+"px",async({page},testInfo)=>{
    await page.setViewportSize({width,height:900});
    await mockClub(page,{loggedIn:true,me:{...member,phone_last4:"",email:"cliente@example.invalid",birth_day:null,birth_month:null,
      marketing_opt_in:false,session_expires_at:new Date(Date.now()+170*86400000).toISOString()}});
    const patches:Record<string,unknown>[]=[];
    await page.route("**/api/v1/public/clubs/*/me/profile/",r=>{const body=r.request().postDataJSON();patches.push(body);
      return r.fulfill({contentType:"application/json",body:JSON.stringify({updated:true,profile:{display_name:"Cliente QA",
        email:"cliente@example.invalid",phone_last4:body.phone?"7777":"",birth_day:body.birth_day??null,birth_month:body.birth_month??null,
        marketing_opt_in:Boolean(body.marketing_opt_in)}})});});
    await page.goto("/clube/loja-jardim");
    await page.getByRole("button",{name:/Complete seu perfil/}).click();
    await expect(page).toHaveURL(/\/clube\/loja-jardim\/perfil$/);
    await expect(page.getByRole("progressbar",{name:"Perfil completo"})).toHaveAttribute("aria-valuenow","33");
    await page.getByRole("textbox",{name:/Celular/}).fill("(31) 98888-7777");
    await page.getByRole("combobox",{name:"Dia do aniversário"}).selectOption("12");
    await page.getByRole("combobox",{name:"Mês do aniversário"}).selectOption("3");
    await page.getByRole("button",{name:"Salvar perfil"}).click();
    await expect(page.getByText("Perfil atualizado.")).toBeVisible();
    expect(patches[0]).toEqual({phone:"(31) 98888-7777",birth_day:12,birth_month:3});
    await expect(page.getByRole("progressbar",{name:"Perfil completo"})).toHaveAttribute("aria-valuenow","100");
    const toggle=page.getByRole("switch",{name:"Receber ofertas por e-mail"});
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked","true");
    await expect(page.getByRole("heading",{name:"App do clube"})).toBeVisible();
    await expect(page.getByText("Este aparelho fica conectado até",{exact:false})).toBeVisible();
    await expect(page.getByRole("link",{name:"Baixar meus dados"})).toHaveAttribute("href","/api/v1/public/clubs/loja-jardim/me/export/");
    await noOverflow(page);
    await page.screenshot({path:testInfo.outputPath("club-profile-"+width+".png"),fullPage:true});
    await page.getByRole("button",{name:"Sair desta conta"}).click();
    await expect(page.getByRole("heading",{name:"Quero participar"})).toBeVisible();
  });
}

test("Oferta de campanha aparece em Para você com prazo e aviso honesto",async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});
  const ends=new Date(Date.now()+5*86400000);
  const iso=ends.getFullYear()+"-"+String(ends.getMonth()+1).padStart(2,"0")+"-"+String(ends.getDate()).padStart(2,"0");
  await mockClub(page,{loggedIn:true,me:{...member,offers:[{id:"o1",goal:"reactivation",title:"Sentimos sua falta: +200 pontos",
    message:"Compre até "+iso.slice(8)+"/"+iso.slice(5,7)+" e ganhe 200 pontos extras.",bonus_points:200,multiplier:null,ends_on:iso}]}});
  await page.goto("/clube/loja-jardim");
  const offers=page.getByRole("region",{name:"Para você"});
  await expect(offers).toContainText("Sentimos sua falta: +200 pontos");
  await expect(offers).toContainText("os pontos entram quando a loja ativar o clube");
  await expect(offers).toContainText(/Faltam [56] dias/);
  await page.screenshot({path:testInfo.outputPath("club-offer-390.png"),fullPage:true});
});

test("App do clube usa o manifest da loja",async({page})=>{
  await mockClub(page);
  await page.goto("/clube/loja-jardim");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href","/api/v1/public/clubs/loja-jardim/manifest.webmanifest");
  await expect(page.locator('meta[name="theme-color"]').first()).toHaveAttribute("content","#0B4FA8");
});
