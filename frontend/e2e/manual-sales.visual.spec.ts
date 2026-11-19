import {expect,test,type Page} from "@playwright/test";

/* Vendas em 3 abas: Balcão (registrar, vale, desfazer), Conferir (aprovar, alertas,
   lote) e Pedidos (balcão + site numa lista). Dados sintéticos. */

const tenant={id:"a904014f-83df-4a04-a20a-b24062fb6433",name:"Loja Balcão",slug:"loja-balcao",status:"active",role:"owner"};
const member={
  id:"bff72f53-1234-481a-8524-ef6fc310ff10",customer_reference:null,display_name:"Ana Souza",
  contact_email:"ana@example.invalid",status:"active",consented_at:"2026-11-12T12:00:00Z",joined_at:"2026-11-12T12:00:00Z",
  last_program_activity_at:null,consent_channel:"customer_portal",points_balance:null,cashback_balance_cents:null,
  cashback_pending_cents:null,cashback_reserved_cents:null,balance_status:"not_implemented",
};
const now=new Date().toISOString();
const sale=(over:Record<string,unknown>)=>({
  id:"0cb247c3-0cc5-499b-834a-8870c9328d41",channel:"counter",reference:"CUPOM-0042",participant_id:member.id,
  participant_name:"Ana Souza",eligible_amount_cents:10000,reported_paid_at:now,evidence_reference:"CUPOM-0042",
  state:"awaiting_review",submitted_by_me:true,reviewed_by_me:false,review_mode:null,review_note:null,created_at:now,reviewed_at:null,
  points_credited:false,cashback_credited:false,points_preview:300,points_capped:false,points_issued:null,
  redemption:null,alerts:[],can_undo:false,submitted_by_name:"bhvidal",...over,
});
const wallet={pilot_active:true,available:2340,pending:0,reserved:0,
  rewards:[{id:"5b0c1b52-0000-4000-8000-000000000020",title:"Vale R$ 20",points_cost:2000,discount_cents:2000,min_order_cents:8000,affordable:true,exhausted:false},
   {id:"5b0c1b52-0000-4000-8000-000000000030",title:"Vale R$ 30",points_cost:3000,discount_cents:3000,min_order_cents:12000,affordable:false,exhausted:false}],
  next_reward:{title:"Vale R$ 30",points_cost:3000,missing:660,discount_cents:3000}};

async function mock(page:Page,items:unknown[]=[],pilot=true){
  await page.context().addCookies([{name:"csrftoken",value:"sales-csrf-synthetic-qa",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    authenticated:true,user:{username:"sales-qa",display_name:"QA Lojista"},tenants:[tenant]})}));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    source:"verified_opt_in_only",data_status:"consent_verified",summary:{total:1,active:1,paused:0},total_filtered:1,limit:20,
    offset:0,items:[member],note:""})}));
  await page.route("**/api/v1/tenants/**/participants/by-phone/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    match:{id:member.id,display_name:"Ana Souza",phone_last4:"1170",status:"active"}})}));
  await page.route("**/api/v1/tenants/**/sales/counter/participants/**/wallet/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify(wallet)}));
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>{
    if(r.request().method()==="GET")return r.fulfill({contentType:"application/json",body:JSON.stringify({
      mode:pilot?"pilot_points":"manual_review_only",points_credited:false,pilot_active:pilot,items})});
    return r.fulfill({status:201,contentType:"application/json",body:JSON.stringify({already_recorded:false,sale:sale({})})});
  });
  await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    mode:"draft_only",activation_available:false,rule:{version:1,points:3,per_cents:100,hold_days:7,validity_days:90}})}));
  await page.route("**/api/v1/tenants/**/loyalty/reward-drafts/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({items:[]})}));
  await page.route("**/api/v1/tenants/**/nuvemshop/orders/recent/preview/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    mode:"read_only",source:"nuvemshop_live_read_only",page:1,page_size:10,points_credited:false,coupons_created:false,read_only:true,note:"",
    items:[
     {order_id:"9001",order_number:"14174",source:"nuvemshop_live_read_only",order_status:"open",payment_status:"paid",paid_at:now,
      reported_total_cents:13205,currency:"BRL",reported_customer_paid_cents:13205,reported_payment_differs_from_total:false,
      reported_paid_amount_is_not_psp_proof:true,participant_verified:false,review_status:"customer_not_verified",
      credit_eligible:false,cashback_created:false,writes_performed:0,note:""},
     {order_id:"9002",order_number:"14171",source:"nuvemshop_live_read_only",order_status:"open",payment_status:"voided",paid_at:null,
      reported_total_cents:24440,currency:"BRL",reported_customer_paid_cents:null,reported_payment_differs_from_total:null,
      reported_paid_amount_is_not_psp_proof:true,participant_verified:false,review_status:"blocked_cancelled",
      credit_eligible:false,cashback_created:false,writes_performed:0,note:""}]})}));
}
async function openSales(page:Page,width:number){
  await page.goto("/app/visao-geral");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:"Vendas"}).click();
  await expect(page.getByRole("tab",{name:"Balcão"})).toHaveAttribute("aria-selected","true");
}
const noScroll=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);

for(const width of [390,768,1440]){
  test("Balcão: celular acha a cliente, aplica o vale e mostra os pontos em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});
    const mine=sale({id:"11111111-1111-4111-8111-111111111111",can_undo:true,redemption:{title:"Vale R$ 20",points:2000,discount_cents:2000,state:"reserved"},
      eligible_amount_cents:15776,points_preview:413});
    await mock(page,[mine]);
    let body:Record<string,unknown>|null=null;
    await page.route("**/api/v1/tenants/**/sales/manual/",r=>{if(r.request().method()==="POST")body=r.request().postDataJSON();return r.fallback();});
    await openSales(page,width);
    await page.locator("#vf-sale-phone").fill("31988421170");
    await expect(page.getByText("2.340 pts liberados")).toBeVisible();
    await page.getByLabel("Valor da compra").fill("157,76");
    await page.getByText("Vale R$ 20",{exact:true}).first().click();
    await expect(page.getByLabel("Conta com o vale")).toContainText("R$ 137,76");
    await expect(page.getByText("+413",{exact:false}).first()).toBeVisible();
    await expect(page.getByText("Diga para Ana",{exact:false})).toHaveCount(0); // meta longe: sem dica
    await expect(page.getByRole("button",{name:"Desfazer"})).toBeVisible();
    await noScroll(page);
    await page.screenshot({path:info.outputPath("balcao-"+width+".png"),fullPage:true});
    await page.getByRole("button",{name:/Registrar venda/}).click();
    await expect(page.getByText("Venda registrada com o Vale R$ 20",{exact:false})).toBeVisible();
    expect(body).toMatchObject({participant_id:member.id,reward_id:wallet.rewards[0].id,eligible_amount_cents:15776});
    expect(String((body as unknown as {reference:string}).reference)).toMatch(/^SEM-CUPOM-/);
  });

  test("Conferir: alerta separa a venda estranha e o lote confirma as normais em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});
    await mock(page,[
      sale({id:"a1",participant_name:"Bruno Vidal",eligible_amount_cents:900000,points_preview:1500,points_capped:true,alerts:["57× o ticket médio","registrada fora do horário comercial"]}),
      sale({id:"a2",participant_name:"Marcos Lima",eligible_amount_cents:6490,points_preview:194,evidence_reference:"CUPOM-0563"}),
      sale({id:"a3",participant_name:"Patrícia Rocha",eligible_amount_cents:21200,points_preview:636,evidence_reference:"SEM-CUPOM-ABC-1234"}),
    ]);
    let batch:unknown=null;
    await page.route("**/api/v1/tenants/**/sales/manual/confirm-batch/",r=>{batch=r.request().postDataJSON();
      return r.fulfill({contentType:"application/json",body:JSON.stringify({confirmed:["a2","a3"],skipped:[],points:830})});});
    await openSales(page,width);
    await page.getByRole("tab",{name:/Conferir/}).click();
    await expect(page.getByText("57× o ticket médio")).toBeVisible();
    await expect(page.getByText("sem cupom",{exact:false})).toBeVisible();
    await noScroll(page);
    await page.screenshot({path:info.outputPath("conferir-"+width+".png"),fullPage:true});
    await page.getByRole("button",{name:"Confirmar 2 sem alerta"}).click();
    await expect(page.getByText("2 vendas confirmadas · +830 pontos.")).toBeVisible();
    expect(batch).toEqual({ids:["a2","a3"]});
  });

  test("Pedidos: balcão e site numa lista, cancelado apagado em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});
    await mock(page,[sale({state:"verified_manual",points_issued:300})]);
    await openSales(page,width);
    await page.getByRole("tab",{name:"Pedidos"}).click();
    const list=page.getByRole("list",{name:"Pedidos"});
    await expect(list.getByText("Ana Souza")).toBeVisible();
    await expect(list.getByText("#14174 · fora do clube")).toBeVisible();
    await expect(list.locator(".is-dim")).toContainText("Cancelado");
    await page.getByPlaceholder("Nome, nº do pedido ou cupom").fill("14174");
    await expect(list.locator("li")).toHaveCount(1);
    await noScroll(page);
    await page.getByPlaceholder("Nome, nº do pedido ou cupom").fill("");
    await page.screenshot({path:info.outputPath("pedidos-"+width+".png"),fullPage:true});
  });
}

test("Confirmar uma venda informa os pontos e quando liberam",async({page})=>{
  await mock(page,[sale({id:"b1"})]);
  let review:unknown=null;
  await page.route("**/api/v1/tenants/**/sales/manual/b1/review/",r=>{review=r.request().postDataJSON();
    return r.fulfill({contentType:"application/json",body:JSON.stringify({sale:sale({id:"b1",state:"verified_manual"}),manual_evidence_reviewed:true,
      review_mode:"self_review",independent_payment_proof:false,points_credited:true,points:300,points_reason:"granted"})});});
  await openSales(page,1440);
  await page.getByRole("tab",{name:/Conferir/}).click();
  await page.getByRole("button",{name:"Confirmar",exact:true}).click();
  await expect(page.getByText("Venda confirmada: +300 pontos para Ana, liberados em 7 dias.")).toBeVisible();
  expect(review).toMatchObject({decision:"approve"});
});

test("Recusar pede confirmação e não credita pontos",async({page})=>{
  await mock(page,[sale({id:"b2"})]);
  await page.route("**/api/v1/tenants/**/sales/manual/b2/review/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({
    sale:sale({id:"b2",state:"rejected"}),manual_evidence_reviewed:true,review_mode:"self_review",independent_payment_proof:false,
    points_credited:false,points:0,points_reason:"rejected"})}));
  await openSales(page,1440);
  await page.getByRole("tab",{name:/Conferir/}).click();
  await page.getByRole("button",{name:"Recusar venda de Ana Souza"}).click();
  await page.getByRole("button",{name:"Recusar venda",exact:true}).click();
  await expect(page.getByText("Venda recusada: nenhum ponto foi creditado.")).toBeVisible();
});

test("Sem piloto ativo, o balcão avisa que a venda não gera crédito",async({page})=>{
  await mock(page,[],false);
  await page.route("**/api/v1/tenants/**/sales/counter/participants/**/wallet/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify({...wallet,pilot_active:false})}));
  await openSales(page,1440);
  await page.locator("#vf-sale-phone").fill("31988421170");
  await page.getByLabel("Valor da compra").fill("100,00");
  await expect(page.getByText("Os pontos estão desligados nesta loja",{exact:false})).toBeVisible();
  await expect(page.getByText("pode usar um vale agora",{exact:false})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Registrar venda",exact:true})).toBeVisible();
});

test("Cliente fora do clube: venda guardada com o celular, cupom opcional",async({page})=>{
  await mock(page);
  let body:Record<string,unknown>|null=null;
  await page.route("**/api/v1/tenants/**/participants/by-phone/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({match:null})}));
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>{
    if(r.request().method()!=="POST")return r.fallback();
    body=r.request().postDataJSON();
    return r.fulfill({status:201,contentType:"application/json",body:JSON.stringify({already_recorded:false,sale:{state:"awaiting_member"}})});
  });
  await openSales(page,1440);
  await page.locator("#vf-sale-phone").fill("(31) 98888-7777");
  await expect(page.getByText("(31) 98888-7777 não está no clube")).toBeVisible();
  await page.getByLabel("Valor da compra").fill("59,90");
  await page.getByText("+ Cupom fiscal ou outra data").click();
  await page.getByLabel("Número do cupom ou recibo").fill("0071");
  await page.getByRole("button",{name:"Registrar venda",exact:true}).click();
  await expect(page.getByText("Venda guardada com o celular do cliente.",{exact:false})).toBeVisible();
  expect(body).toMatchObject({participant_id:null,customer_phone:"(31) 98888-7777",reference:"CUPOM-0071"});
});

test("Sem cliente escolhido, o registro explica o que falta",async({page})=>{
  await mock(page);
  await openSales(page,1440);
  await page.getByLabel("Valor da compra").fill("59,90");
  await page.getByRole("button",{name:"Registrar venda",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Escolha o cliente");
});

test("Dica para o vendedor só aparece quando a próxima recompensa está perto",async({page})=>{
  await mock(page);
  await page.route("**/api/v1/tenants/**/sales/counter/participants/**/wallet/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify({...wallet,available:1800,rewards:wallet.rewards.map(x=>({...x,affordable:false}))})}));
  await openSales(page,1440);
  await page.locator("#vf-sale-phone").fill("31988421170");
  await page.getByLabel("Valor da compra").fill("100,00");
  await expect(page.getByText("Diga para Ana: “com mais R$ 300,00 em compras você ganha Vale R$ 30.”")).toBeVisible();
});

test("Máscara de celular: formata ao digitar, aceita +55 e só busca com o número completo",async({page})=>{
  await mock(page);
  const lookups:string[]=[];
  await page.route("**/api/v1/tenants/**/participants/by-phone/",r=>{lookups.push(r.request().postDataJSON().phone);
    return r.fulfill({contentType:"application/json",body:JSON.stringify({match:null})});});
  await page.setViewportSize({width:390,height:900});
  await openSales(page,390);
  const input=page.locator("#vf-sale-phone");
  await input.pressSequentially("3198842117",{delay:20});
  await expect(input).toHaveValue("(31) 98842-117");
  await page.waitForTimeout(600);
  expect(lookups).toEqual([]);                       // celular com 10 dígitos ainda está incompleto
  await expect(page.getByText("Continue digitando: celular tem 11 dígitos com o DDD.")).toBeVisible();
  await input.fill("+55 (31) 9 8842-1170");
  await expect(page.getByText("(31) 98842-1170 não está no clube")).toBeVisible();
  expect(lookups).toEqual(["(31) 98842-1170"]);
});

test("Celular não achado: busca pelo nome e salva o celular no cadastro",async({page})=>{
  await mock(page);
  let saved:unknown=null;
  await page.route("**/api/v1/tenants/**/participants/by-phone/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({match:null})}));
  await page.route("**/api/v1/tenants/**/participants/*/phone/",r=>{saved=r.request().postDataJSON();
    return r.fulfill({contentType:"application/json",body:JSON.stringify({participant:{id:member.id,display_name:"Ana Souza",phone_last4:"1170",status:"active"}})});});
  await openSales(page,1440);
  await page.locator("#vf-sale-phone").fill("31988421170");
  await page.getByRole("button",{name:"É do clube? Buscar pelo nome"}).click();
  await page.locator("#vf-sale-client").fill("Ana");
  await page.getByRole("list",{name:"Participantes encontrados"}).getByRole("button",{name:/Ana Souza/}).click();
  await page.getByRole("button",{name:"Salvar celular"}).click();
  await expect(page.getByText("Celular salvo no cadastro de Ana.")).toBeVisible();
  expect(saved).toEqual({phone:"(31) 98842-1170",customer_informed:true});
});
