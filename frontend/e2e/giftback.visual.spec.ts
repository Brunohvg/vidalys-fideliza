import {expect,test,type Page} from "@playwright/test";

/* Giftback como modo do programa: escolher e configurar no Meu clube, usar o crédito
   no balcão e ver o crédito em reais no Meu Clube do cliente. Dados sintéticos. */

const tenant={id:"0f6c2b1a-2222-4b3c-8d4e-5f6a7b8c9d0e",name:"Loja Gift",slug:"loja-gift",status:"active",role:"owner",platform:"independent"};
const program={mode:"giftback",percent_bps:1000,cap_cents:2000,min_order_cents:8000,validity_days:30,hold_days:7};
const json=(body:unknown,status=200)=>({status,contentType:"application/json",body:JSON.stringify(body)});
const noOverflow=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);

async function merchant(page:Page){
  await page.context().addCookies([{name:"csrftoken",value:"gift-csrf-qa",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:true,user:{username:"qa",display_name:"QA"},tenants:[tenant]})));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill(json({source:"verified_opt_in_only",data_status:"consent_verified",
    summary:{total:1,active:1,paused:0},total_filtered:1,limit:20,offset:0,items:[]})));
  await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",r=>r.fulfill(json({mode:"draft_only",activation_available:false,rule:null})));
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",r=>r.fulfill(json({items:[]})));
}
const go=async(page:Page,width:number,nav:string)=>{
  await page.goto("/app/visao-geral");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:new RegExp("^"+nav+"(\\s|$)")}).click();
};

for(const width of [390,1440]){
  test("Meu clube: escolher giftback com valores recomendados e simulação em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});await merchant(page);
    let saved:unknown=null;
    let state={mode:"points",saved:false,giftback_bps:1000,giftback_cap_cents:2000,giftback_min_order_cents:8000,
      giftback_validity_days:30,giftback_hold_days:7,average_ticket_cents:15776};
    await page.route("**/api/v1/tenants/**/loyalty/program-mode/",r=>{
      if(r.request().method()==="POST"){saved=r.request().postDataJSON();state={...state,...(saved as object),saved:true};}
      return r.fulfill(json(state));
    });
    await go(page,width,"Meu clube");
    await page.getByRole("radio",{name:/Giftback/}).click();
    await expect(page.getByText("Compra de R$ 157,76 gera R$ 15,77 de crédito")).toBeVisible();
    await page.getByRole("group",{name:"Teto do crédito"}).getByRole("button",{name:"R$ 10"}).click();
    await expect(page.getByText("Compra de R$ 157,76 gera R$ 10,00 de crédito")).toBeVisible();
    await page.getByRole("button",{name:"Usar recomendado"}).click();
    await noOverflow(page);
    await page.locator(".pm-root").screenshot({path:info.outputPath("giftback-modo-"+width+".png")});
    await page.getByRole("button",{name:"Salvar giftback"}).click();
    await expect(page.getByText("Giftback salvo.",{exact:false})).toBeVisible();
    expect(saved).toEqual({mode:"giftback",giftback_bps:1000,giftback_cap_cents:2000,giftback_min_order_cents:8000,giftback_validity_days:30,giftback_hold_days:7});
    await page.getByRole("tab",{name:"2. Como usar"}).click();
    await expect(page.getByRole("heading",{name:"No giftback, não há faixas para montar"})).toBeVisible();
  });

  test("Balcão: crédito de giftback aplicado e novo crédito calculado em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});await merchant(page);
    let body:Record<string,unknown>|null=null;
    await page.route("**/api/v1/tenants/**/sales/manual/",r=>{
      if(r.request().method()==="POST"){body=r.request().postDataJSON();
        return r.fulfill(json({already_recorded:false,sale:{id:"s1",state:"awaiting_review"}},201));}
      return r.fulfill(json({mode:"pilot_points",points_credited:false,pilot_active:true,program,items:[]}));
    });
    await page.route("**/api/v1/tenants/**/participants/by-phone/",r=>r.fulfill(json({match:{id:"p1",display_name:"Ana Souza",phone_last4:"1170",status:"active"}})));
    await page.route("**/api/v1/tenants/**/sales/counter/participants/**/wallet/",r=>r.fulfill(json({program,
      credit:{available_cents:1577,min_order_cents:8000},pilot_active:true,available:1577,pending:0,reserved:0,rewards:[],next_reward:null})));
    await go(page,width,"Vendas");
    await page.locator("#vf-sale-phone").fill("31988421170");
    await expect(page.getByText("R$ 15,77 de crédito liberado")).toBeVisible();
    await page.getByLabel("Valor da compra").fill("120,00");
    await page.getByText("Crédito de R$ 15,77").click();
    await expect(page.getByLabel("Conta com o vale")).toContainText("R$ 104,23");
    await expect(page.locator(".vs-ticket")).toContainText("+R$ 10,42");
    await noOverflow(page);
    await page.screenshot({path:info.outputPath("giftback-balcao-"+width+".png"),fullPage:true});
    await page.getByRole("button",{name:/Registrar venda/}).click();
    await expect(page.getByText("Venda registrada com R$ 15,77 de crédito.",{exact:false})).toBeVisible();
    expect(body).toMatchObject({participant_id:"p1",use_credit:true,eligible_amount_cents:12000});
    expect(body).not.toHaveProperty("reward_id");
  });
}

test("Balcão bloqueia crédito abaixo da compra mínima",async({page})=>{
  await merchant(page);
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill(json({mode:"pilot_points",points_credited:false,pilot_active:true,program,items:[]})));
  await page.route("**/api/v1/tenants/**/participants/by-phone/",r=>r.fulfill(json({match:{id:"p1",display_name:"Ana Souza",phone_last4:"1170",status:"active"}})));
  await page.route("**/api/v1/tenants/**/sales/counter/participants/**/wallet/",r=>r.fulfill(json({program,
    credit:{available_cents:1577,min_order_cents:8000},pilot_active:true,available:1577,pending:0,reserved:0,rewards:[],next_reward:null})));
  await go(page,1440,"Vendas");
  await page.locator("#vf-sale-phone").fill("31988421170");
  await page.getByLabel("Valor da compra").fill("50,00");
  await page.getByText("Crédito de R$ 15,77").click();
  await expect(page.getByText("O crédito vale em compras a partir de R$ 80,00.").first()).toBeVisible();
});

for(const width of [390,1440]){
  test("Meu Clube do cliente mostra crédito em reais e como usar em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:900});
    const terms={id:"t1",version:"v1",title:"Regulamento",body:"Regras.",privacy_notice:"Dados.",approved_at:"2026-11-13T12:00:00Z"};
    const club={store_name:"Loja Gift",store_slug:"loja-gift",branding:{program_name:"Clube Gift",primary_color:"#0B4FA8",accent_color:"#FF8A3D",support_email:""},
      terms,signup_available:true,points_enabled:true,rewards_enabled:false,redemption_enabled:false,published_rewards:[],
      earning:null,program};
    const me={store_name:"Loja Gift",display_name:"Ana Souza",phone_last4:"1170",status:"active",joined_at:"2026-11-13T12:30:00Z",terms,
      points_balance:1577,points_pending:892,points_expiring:1577,points_status:"counter",redemption_place:"counter",program,
      available_rewards:[],transactions:[],redemption_enabled:false,orders_verified:false,note:""};
    await page.context().addCookies([{name:"csrftoken",value:"csrf-member-gift",url:"http://127.0.0.1:4173"}]);
    await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:false,user:null,tenants:[]})));
    await page.route("**/api/v1/public/clubs/*/",r=>r.fulfill(json(club)));
    await page.route("**/api/v1/public/clubs/*/me/",r=>r.fulfill(json(me)));
    await page.goto("/clube/loja-gift");
    await expect(page.getByText("R$ 15,77",{exact:true})).toBeVisible();
    await expect(page.getByText("+R$ 8,92 a liberar",{exact:false})).toBeVisible();
    await expect(page.getByText("de crédito vence em breve",{exact:false})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Próxima troca"})).toHaveCount(0);
    await noOverflow(page);
    await page.screenshot({path:info.outputPath("giftback-cliente-"+width+".png"),fullPage:true});
  });
}

for(const width of [390,1440]){
  test("Meu clube: 3 passos de ativação, ativar e pausar o piloto em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});await merchant(page);
    await page.route("**/api/v1/tenants/**/loyalty/program-mode/",r=>r.fulfill(json({mode:"giftback",saved:true,giftback_bps:1000,
      giftback_cap_cents:2000,giftback_min_order_cents:8000,giftback_validity_days:30,giftback_hold_days:7,average_ticket_cents:15776})));
    let pilot={allowed:true,active:false,per_sale_cap_points:2000,budget_points:50000,issued_points:12400,activated_at:null as string|null,
      paused_at:null as string|null,rule:null,counter_rewards:0,program,notices:{reachable_members:3,emails_queued:2}};
    const posts:unknown[]=[];
    await page.route("**/api/v1/tenants/**/sales/pilot/",r=>{
      if(r.request().method()==="POST"){const b=r.request().postDataJSON();posts.push(b);pilot={...pilot,...b};}
      return r.fulfill(json(pilot));
    });
    await go(page,width,"Meu clube");
    const steps=page.getByRole("navigation",{name:"Ativação do clube"});
    await expect(steps).toContainText("Giftback em uso");
    await expect(steps.locator("[aria-current=step]")).toContainText("Ative no balcão");
    await steps.getByRole("button",{name:"Ir para a ativação"}).click();
    const card=page.locator("#vf-pilot-card");
    await expect(card).toContainText("R$ 124,00 de R$ 500,00");
    await expect(card).toContainText("Giftback salvo: 10% de volta");
    await expect(card).toContainText("3 clientes hoje · 2 avisos enviados");
    await card.getByRole("button",{name:"Ativar no balcão"}).click();
    await expect(page.getByText("Ativado. Confirme",{exact:false})).toBeVisible();
    await expect(steps).toContainText("Ativo: confirme as vendas");
    await noOverflow(page);
    await steps.screenshot({path:info.outputPath("passos-"+width+".png")});
    await card.getByRole("button",{name:"Pausar agora"}).click();
    await expect(page.getByText("Pausado. Novas conferências não geram crédito",{exact:false})).toBeVisible();
    await expect(card).not.toContainText("homologação");
    expect(posts).toEqual([{active:true},{active:false}]);
  });
}

test("Conferir no giftback fala em crédito, não em pontos",async({page})=>{
  await merchant(page);
  const now=new Date().toISOString();
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill(json({mode:"pilot_points",points_credited:false,pilot_active:true,program,
    items:[{id:"g1",channel:"counter",reference:"CUPOM-1",participant_id:"p1",participant_name:"Ana Souza",eligible_amount_cents:15776,
      reported_paid_at:now,evidence_reference:"CUPOM-1",state:"awaiting_review",submitted_by_me:true,reviewed_by_me:false,review_mode:null,
      review_note:null,created_at:now,reviewed_at:null,points_credited:false,cashback_credited:false,points_preview:1577,alerts:[],can_undo:false}]})));
  await page.route("**/api/v1/tenants/**/sales/manual/g1/review/",r=>r.fulfill(json({sale:{},manual_evidence_reviewed:true,review_mode:"self_review",
    independent_payment_proof:false,points_credited:true,points:1577,points_reason:"granted"})));
  await go(page,1440,"Vendas");
  await page.getByRole("tab",{name:/Conferir/}).click();
  await expect(page.getByText("O crédito só entra depois de confirmar.",{exact:false})).toBeVisible();
  await expect(page.getByText("≈ +R$ 15,77")).toBeVisible();
  await page.getByRole("button",{name:"Confirmar",exact:true}).click();
  await expect(page.getByText("Venda confirmada: +R$ 15,77 de crédito para Ana, liberado em 7 dias.")).toBeVisible();
});

/* ---------- Resgate no site (cupom único) ---------- */
const siteCoupon={code:"LOJAGI-7K2Q9MXP",discount_cents:1577,min_order_cents:8000,expires_at:"2026-12-20T03:00:00Z",
  apply_url:"https://loja.example/discount/LOJAGI-7K2Q9MXP",source:"giftback",title:"Crédito de giftback",state:"issued"};
async function member(page:Page,me:Record<string,unknown>,clubProgram:unknown=program){
  const terms={id:"t1",version:"v1",title:"Regulamento",body:"Regras.",privacy_notice:"Dados.",approved_at:"2026-11-13T12:00:00Z"};
  const club={store_name:"Loja Gift",store_slug:"loja-gift",branding:{program_name:"Clube Gift",primary_color:"#0B4FA8",accent_color:"#FF8A3D",support_email:""},
    terms,signup_available:true,points_enabled:true,rewards_enabled:false,redemption_enabled:false,published_rewards:[],earning:null,program:clubProgram};
  const base={store_name:"Loja Gift",display_name:"Ana Souza",phone_last4:"1170",status:"active",joined_at:"2026-11-13T12:30:00Z",terms,
    points_pending:0,points_expiring:0,points_status:"counter",redemption_place:"counter",program:clubProgram,
    available_rewards:[],transactions:[],redemption_enabled:false,orders_verified:false,note:""};
  await page.context().addCookies([{name:"csrftoken",value:"csrf-member-site",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:false,user:null,tenants:[]})));
  await page.route("**/api/v1/public/clubs/*/",r=>r.fulfill(json(club)));
  let current={...base,...me};
  await page.route("**/api/v1/public/clubs/*/me/",r=>r.fulfill(json(current)));
  return {set:(next:Record<string,unknown>)=>{current={...base,...next};}};
}

for(const width of [390,1440]){
  test("Meu Clube mostra o cupom do site com código, copiar e comprar em "+width+"px",async({page,context},info)=>{
    await context.grantPermissions(["clipboard-read","clipboard-write"]);
    await page.setViewportSize({width,height:900});
    await member(page,{points_balance:0,site:{coupons_enabled:true,coupons:[siteCoupon]}});
    await page.goto("/clube/loja-gift");
    await expect(page.getByText("R$ 15,77",{exact:true}).first()).toBeVisible();          // saldo inclui o cupom
    const ticket=page.getByRole("region",{name:/Cupom para o site/});
    await expect(ticket).toContainText("LOJAGI-7K2Q9MXP");
    await expect(ticket).toContainText("compra a partir de R$ 80,00");
    await expect(ticket.getByRole("link",{name:"Comprar com o cupom"})).toHaveAttribute("href",siteCoupon.apply_url);
    await ticket.getByRole("button",{name:/Copiar cupom/}).click();
    expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe("LOJAGI-7K2Q9MXP");
    await noOverflow(page);
    await ticket.screenshot({path:info.outputPath("cupom-site-"+width+".png")});
  });
}

test("Sem cupom ainda: cliente gera o cupom do crédito com um toque",async({page})=>{
  const m=await member(page,{points_balance:1577,site:{coupons_enabled:true,coupons:[]}});
  let posted:unknown=null;
  await page.route("**/api/v1/public/clubs/*/coupons/",r=>{posted=r.request().postDataJSON();
    m.set({points_balance:0,site:{coupons_enabled:true,coupons:[siteCoupon]}});
    return r.fulfill(json({coupon:siteCoupon},201));});
  await page.goto("/clube/loja-gift");
  await page.getByRole("button",{name:"Gerar cupom"}).click();
  await expect(page.getByRole("region",{name:/Cupom para o site/})).toContainText("LOJAGI-7K2Q9MXP");
  expect(posted).toEqual({});
});

test("Nuvemshop não confirmou: cliente vê \"confirmando\", sem código, e o saldo guardado",async({page},info)=>{
  await page.setViewportSize({width:390,height:844});
  const m=await member(page,{points_balance:1577,site:{coupons_enabled:true,coupons:[]}});
  const pending={...siteCoupon,code:"",apply_url:"",state:"uncertain"};
  await page.route("**/api/v1/public/clubs/*/coupons/",r=>{
    m.set({points_balance:0,site:{coupons_enabled:true,coupons:[pending]}});
    return r.fulfill(json({detail:"Estamos confirmando seu cupom com a loja. Seu saldo continua guardado; volte em alguns minutos."},409));});
  await page.goto("/clube/loja-gift");
  await page.getByRole("button",{name:"Gerar cupom"}).click();
  const card=page.getByRole("status",{name:/Cupom em confirmação/});
  await expect(card).toContainText("Confirmando seu cupom de R$ 15,77");
  await expect(card).toContainText("Seu saldo está guardado");
  await expect(page.getByRole("button",{name:/Copiar cupom/})).toHaveCount(0);
  await expect(page.getByRole("link",{name:"Comprar com o cupom"})).toHaveCount(0);
  await expect(page.getByText("R$ 15,77",{exact:true}).first()).toBeVisible();          // saldo continua aparecendo
  await noOverflow(page);
  await card.screenshot({path:info.outputPath("cupom-confirmando-390.png")});
});

test("Pontos: recompensa vira cupom para o site",async({page})=>{
  const reward={id:"r10",title:"Vale R$ 10",points_cost:1000,discount_cents:1000,min_order_cents:5000,status:"available",
    redemption_unit:"points",redemption_enabled:false};
  const m=await member(page,{points_balance:1200,available_rewards:[reward],site:{coupons_enabled:true,coupons:[]}},{mode:"points"});
  let posted:unknown=null;
  await page.route("**/api/v1/public/clubs/*/coupons/",r=>{posted=r.request().postDataJSON();
    m.set({points_balance:200,available_rewards:[reward],site:{coupons_enabled:true,coupons:[{...siteCoupon,source:"reward",title:"Vale R$ 10",discount_cents:1000,min_order_cents:5000}]}});
    return r.fulfill(json({coupon:siteCoupon},201));});
  await page.goto("/clube/loja-gift");
  await page.locator(".clb-tabs").getByRole("button",{name:"Trocar"}).click();
  await page.getByRole("button",{name:"Cupom para o site"}).click();
  await expect(page.getByRole("region",{name:/Cupom para o site: Vale R\$ 10/})).toBeVisible();
  expect(posted).toEqual({reward_id:"r10"});
});

for(const width of [390,1440]){
  test("Meu clube: seção do site mostra o que falta e liga opções em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});await merchant(page);
    await page.route("**/api/v1/tenants/**/loyalty/program-mode/",r=>r.fulfill(json({mode:"giftback",saved:true,giftback_bps:1000,
      giftback_cap_cents:2000,giftback_min_order_cents:8000,giftback_validity_days:30,giftback_hold_days:7})));
    let pilot={allowed:true,active:true,per_sale_cap_points:2000,budget_points:50000,issued_points:0,activated_at:null,paused_at:null,rule:null,
      counter_rewards:0,program,site:{connected:true,orders_scope:true,coupons_scope:false,webhooks:true,coupons_server:true,earning_ready:true,
      coupons_ready:false,online_earning:true,online_coupons:true,coupon_combines:false,coupons_paused:false,coupons_active:0,coupons_used:0}};
    const posts:unknown[]=[];
    await page.route("**/api/v1/tenants/**/sales/pilot/",r=>{
      if(r.request().method()==="POST"){const b=r.request().postDataJSON();posts.push(b);pilot={...pilot,site:{...pilot.site,...b}};}
      return r.fulfill(json(pilot));
    });
    await go(page,width,"Meu clube");
    const site=page.getByRole("group",{name:"No site (Nuvemshop)"});
    await expect(site).toContainText("Permissão para criar cupons — Em Configurações → Canais");
    await expect(site.getByRole("switch",{name:"Resgate por cupom único no site"})).toBeDisabled();
    await site.getByRole("switch",{name:"Compras pagas no site geram crédito"}).click();
    await expect(page.getByText("Compras pagas no site geram crédito: desligado.")).toBeVisible();
    expect(posts).toEqual([{online_earning:false}]);
    await noOverflow(page);
    await site.screenshot({path:info.outputPath("site-lojista-"+width+".png")});
  });
}
