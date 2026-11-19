import {expect,test,type Page} from "@playwright/test";

/* Início mostra "Hoje no balcão"; Meu clube → Participar convida compradores do site fora do clube. */

const tenant={id:"5d3b8f70-1111-4c2a-9d1e-1a2b3c4d5e6f",name:"Loja Hoje",slug:"loja-hoje",status:"active",role:"owner",platform:"nuvemshop"};
const now=new Date().toISOString();
const sale=(over:Record<string,unknown>)=>({id:crypto.randomUUID(),channel:"counter",reference:"CUPOM-1",participant_id:"p1",participant_name:"Ana",
  eligible_amount_cents:10000,reported_paid_at:now,evidence_reference:"CUPOM-1",state:"verified_manual",submitted_by_me:true,reviewed_by_me:true,
  review_mode:"self_review",review_note:null,created_at:now,reviewed_at:now,points_credited:false,cashback_credited:false,
  points_issued:300,points_preview:300,redemption:null,alerts:[],can_undo:false,...over});
const order=(over:Record<string,unknown>)=>({order_id:"1",order_number:"1",source:"nuvemshop_live_read_only",order_status:"open",payment_status:"paid",
  paid_at:now,reported_total_cents:10000,currency:"BRL",reported_customer_paid_cents:10000,reported_payment_differs_from_total:false,
  reported_paid_amount_is_not_psp_proof:true,participant_verified:false,review_status:"customer_not_verified",credit_eligible:false,
  cashback_created:false,writes_performed:0,note:"",...over});

async function mock(page:Page){
  await page.context().addCookies([{name:"csrftoken",value:"home-csrf-qa",url:"http://127.0.0.1:4173"}]);
  const json=(body:unknown)=>({contentType:"application/json",body:JSON.stringify(body)});
  await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:true,user:{username:"qa",display_name:"Bruno QA"},tenants:[tenant]})));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill(json({source:"verified_opt_in_only",data_status:"consent_verified",
    summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,items:[]})));
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill(json({mode:"pilot_points",points_credited:false,pilot_active:true,items:[
    sale({}),sale({state:"awaiting_review",points_issued:null,points_preview:450,eligible_amount_cents:15000}),
    sale({state:"rejected",eligible_amount_cents:99900}),
    sale({created_at:"2026-01-02T12:00:00Z",eligible_amount_cents:50000})]})));
  await page.route("**/api/v1/tenants/**/nuvemshop/orders/recent/preview/",r=>r.fulfill(json({mode:"read_only",source:"nuvemshop_live_read_only",
    page:1,page_size:10,points_credited:false,coupons_created:false,read_only:true,note:"",items:[
     order({order_id:"a",reported_total_cents:13205}),order({order_id:"b",reported_total_cents:8875}),
     order({order_id:"c",participant_verified:true}),order({order_id:"d",payment_status:"voided",review_status:"blocked_cancelled"})]})));
}
const open=async(page:Page,width:number,nav:string)=>{
  await page.goto("/app/visao-geral");
  if(nav==="Início")return;
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator(".portal-nav").getByRole("button",{name:nav,exact:true}).click();
};

for(const width of [390,1440]){
  test("Início mostra as vendas de hoje sem contar recusadas nem outros dias em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:1000});await mock(page);
    await open(page,width,"Início");
    const today=page.getByRole("region",{name:"Hoje no balcão"});
    await expect(today).toContainText("2");
    await expect(today).toContainText("R$ 250,00");
    await expect(today).toContainText("750");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
    await today.screenshot({path:info.outputPath("hoje-"+width+".png")});
  });

  test("Meu clube convida compradores pagos do site que não são do clube em "+width+"px",async({page,context},info)=>{
    await context.grantPermissions(["clipboard-read","clipboard-write"]);
    await page.setViewportSize({width,height:1000});await mock(page);
    await open(page,width,"Meu clube");
    await page.getByRole("tab",{name:"3. Quem participa"}).click();
    const card=page.getByRole("region",{name:/2 compradores recentes do site/});
    await expect(card).toContainText("R$ 220,80");
    await card.getByRole("button",{name:"Copiar convite"}).click();
    await expect(card.getByRole("button",{name:"Mensagem copiada"})).toBeVisible();
    expect(await page.evaluate(()=>navigator.clipboard.readText())).toContain("/clube/loja-hoje");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
    await card.screenshot({path:info.outputPath("convite-"+width+".png")});
  });
}
