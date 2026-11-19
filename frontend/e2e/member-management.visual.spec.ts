import {expect,test,type Page} from "@playwright/test";

/* Gestão pelo painel: cadastrar cliente, remover cliente e apagar venda lançada à mão.
   Pedidos do site mostram o crédito que o clube já deu. Dados sintéticos. */

const tenantId="c7ec1a2b-4444-4b3c-8d4e-5f6a7b8c9d0e";
const pid="ff759ffe-8c4a-4dc6-a18f-d6eab4a62003";
const json=(b:unknown,status=200)=>({status,contentType:"application/json",body:JSON.stringify(b)});
const noOverflow=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
const program={mode:"giftback",percent_bps:1000,cap_cents:2000,min_order_cents:8000,validity_days:30,hold_days:7};
const row={id:pid,customer_reference:"",nuvemshop_customer_linked:false,phone_last4:"7777",manual_sales_count:0,manual_sales_reviewed:0,
  manual_sales_pending:0,manual_sales_reported_cents:0,last_manual_sale_at:null,display_name:"Bia Lima",contact_email:"bia@example.invalid",
  status:"active",consented_at:"2026-11-19T10:00:00Z",joined_at:"2026-11-19T10:00:00Z",consent_channel:"merchant_assisted",
  last_program_activity_at:null,points_balance:null,points_pending:null,points_status:"not_active",cashback_balance_cents:null,
  cashback_pending_cents:null,cashback_reserved_cents:null,balance_status:"not_implemented"};
const detail={participant:row,profile:{email_verified:false,marketing_opt_in:false,birth_day:null,birth_month:null,terms_version:"v1"},
  sales:[],offers:[],program,channels:{site:true,counter:false}};

async function merchant(page:Page){
  await page.context().addCookies([{name:"csrftoken",value:"mgmt-csrf",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:true,user:{username:"qa",display_name:"QA"},
    tenants:[{id:tenantId,name:"Loja Gestão",slug:"loja-gestao",status:"active",role:"owner",platform:"nuvemshop"}]})));
  await page.route("**/api/v1/tenants/**/sales/counter/participants/**",r=>r.fulfill(json({detail:"x"},404)));
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill(json({mode:"pilot_points",points_credited:false,
    pilot_active:true,program,channels:{site:true,counter:false},items:[]})));
}

for(const width of [390,1440]){
  test("Cadastrar cliente pede autorização e abre o cadastro em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:900});await merchant(page);
    let created:unknown=null;
    await page.route("**/api/v1/tenants/**/participants/**",r=>{
      const url=r.request().url();
      if(url.includes("/participants/new/")){created=r.request().postDataJSON();return r.fulfill(json({...detail,email_confirmation:"sent"},201));}
      if(url.includes("/participants/"+pid+"/"))return r.fulfill(json(detail));
      return r.fulfill(json({source:"verified_opt_in_only",data_status:"consent_verified",summary:{total:0,active:0,paused:0},
        total_filtered:0,limit:20,offset:0,items:[],note:""}));});
    await page.goto("/app/clientes");
    await page.getByRole("button",{name:"Cadastrar cliente"}).click();
    const form=page.getByRole("form",{name:"Cadastrar cliente"});
    await form.getByLabel("Nome").fill("Bia Lima");
    await form.getByLabel("E-mail").fill("bia@example.invalid");
    await form.getByLabel("Celular (opcional)").fill("31988887777");
    const submit=form.getByRole("button",{name:/Cadastrar/});
    await expect(submit).toBeDisabled();                                   // sem autorização da cliente
    await form.getByLabel("A cliente autorizou entrar no clube e conhece o regulamento").check();
    await noOverflow(page);
    await form.screenshot({path:info.outputPath("cadastrar-cliente-"+width+".png")});
    await submit.click();
    await expect(page.getByRole("heading",{name:"Bia Lima",level:1})).toBeVisible();
    expect(created).toEqual({name:"Bia Lima",email:"bia@example.invalid",phone:"(31) 98888-7777",authorized:true});
    await expect(page.getByRole("button",{name:"Registrar venda"})).toHaveCount(0);   // loja só no site
  });
}

test("Remover cliente explica o que acontece e volta para a lista",async({page})=>{
  await page.setViewportSize({width:1440,height:900});await merchant(page);
  let removed:unknown=null;
  await page.route("**/api/v1/tenants/**/participants/**",r=>{
    const url=r.request().url();
    if(url.includes("/remove/")){removed=r.request().postDataJSON();return r.fulfill(json({removed:true,reversed:1577}));}
    if(url.includes("/participants/"+pid+"/"))return r.fulfill(json(detail));
    return r.fulfill(json({source:"verified_opt_in_only",data_status:"consent_verified",summary:{total:0,active:0,paused:0},
      total_filtered:0,limit:20,offset:0,items:[],note:""}));});
  await page.goto("/app/clientes/"+pid);
  await expect(page.getByRole("button",{name:"Remover do clube"})).toHaveCount(2);   // no topo e em Participação
  await page.getByRole("button",{name:"Remover do clube"}).first().click();
  const box=page.getByRole("group",{name:"Confirmar remoção"});
  await expect(box).toContainText("O saldo dela é zerado");
  await expect(box).toContainText("Não dá para desfazer");
  await box.getByLabel("Motivo (opcional)").fill("pedido da cliente");
  await box.getByRole("button",{name:"Remover definitivamente"}).click();
  await expect(page.getByRole("heading",{name:"Quem faz parte do clube"})).toBeVisible();
  expect(removed).toEqual({confirm:true,reason:"pedido da cliente"});
});

test("Pedidos: anular venda lançada à mão pede motivo; site mostra o crédito dado",async({page},info)=>{
  await page.setViewportSize({width:1440,height:1000});await merchant(page);
  const now=new Date().toISOString();
  let items=[{id:"s1",channel:"counter",reference:"CUPOM-9",participant_id:"p1",participant_name:"Ana Souza",eligible_amount_cents:12000,
    reported_paid_at:now,evidence_reference:"CUPOM-9",state:"awaiting_review",submitted_by_me:true,reviewed_by_me:false,review_mode:null,
    review_note:null,created_at:now,reviewed_at:null,points_credited:false,cashback_credited:false,points_preview:1200,alerts:[],can_undo:false}];
  let posted:unknown=null;
  await page.route("**/api/v1/tenants/**/sales/manual/**",r=>{
    const url=r.request().url();
    if(url.includes("/remove/")){posted=r.request().postDataJSON();items=[];return r.fulfill(json({removed:true,returned:0,reversed:0}));}
    return r.fulfill(json({mode:"pilot_points",points_credited:false,pilot_active:true,program,channels:{site:true,counter:false},items}));});
  await page.route("**/api/v1/tenants/**/nuvemshop/orders/recent/preview/",r=>r.fulfill(json({items:[
    {order_id:"2126595438",order_number:"14185",source:"nuvemshop_live_read_only",order_status:"open",payment_status:"paid",
     paid_at:now,reported_total_cents:6950,currency:"BRL",reported_customer_paid_cents:6950,reported_payment_differs_from_total:false,
     reported_paid_amount_is_not_psp_proof:true,participant_verified:true,review_status:"reported_paid_requires_reconciliation",
     club_units:695}]})));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill(json({source:"verified_opt_in_only",data_status:"consent_verified",
    summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,offset:0,items:[],note:""})));
  await page.goto("/app/vendas");
  const list=page.getByRole("list",{name:"Pedidos"});
  await expect(list).toContainText("+R$ 6,95");                            // crédito do clube no pedido do site
  await list.screenshot({path:info.outputPath("pedidos-anular-1440.png")});
  await list.getByRole("button",{name:"Anular venda de Ana Souza"}).click();
  const box=page.getByRole("group",{name:"Anular venda"});
  const confirm=box.getByRole("button",{name:"Anular venda"});
  await expect(confirm).toBeDisabled();
  await box.getByLabel("Motivo").fill("lançada em dobro");
  await box.screenshot({path:info.outputPath("anular-venda-1440.png")});
  await confirm.click();
  await expect(page.getByText("Venda anulada.")).toBeVisible();
  expect(posted).toEqual({reason:"lançada em dobro"});
  await expect(list).not.toContainText("Ana Souza");
});
