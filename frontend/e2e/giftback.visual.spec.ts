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
      paused_at:null as string|null,rule:null,counter_rewards:0,program};
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
    await card.getByRole("button",{name:"Ativar piloto"}).click();
    await expect(page.getByText("Piloto ativo.",{exact:false})).toBeVisible();
    await expect(steps).toContainText("Ativo: confirme as vendas");
    await noOverflow(page);
    await steps.screenshot({path:info.outputPath("passos-"+width+".png")});
    await card.getByRole("button",{name:"Pausar agora"}).click();
    await expect(page.getByText("Novas conferências não geram crédito",{exact:false})).toBeVisible();
    expect(posts).toEqual([{active:true},{active:false}]);
  });
}

test("Piloto não liberado: passo 3 avisa liberação pela equipe, sem botão",async({page})=>{
  await merchant(page);
  await page.route("**/api/v1/tenants/**/loyalty/program-mode/",r=>r.fulfill(json({mode:"points",saved:false,giftback_bps:1000,
    giftback_cap_cents:2000,giftback_min_order_cents:8000,giftback_validity_days:30,giftback_hold_days:7})));
  await page.route("**/api/v1/tenants/**/sales/pilot/",r=>r.fulfill(json({allowed:false,active:false,per_sale_cap_points:1500,
    budget_points:50000,issued_points:0,activated_at:null,paused_at:null,rule:null,counter_rewards:0,program:{mode:"points"}})));
  await go(page,1440,"Meu clube");
  await expect(page.getByRole("navigation",{name:"Ativação do clube"})).toContainText("Liberação pela equipe Vidalys");
  await expect(page.getByRole("button",{name:"Ativar piloto"})).toHaveCount(0);
  await expect(page.getByText("Não liberado")).toBeVisible();
});

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
