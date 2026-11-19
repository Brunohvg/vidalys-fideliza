import {expect, test, type Page} from "@playwright/test";

/* Página própria do cliente (/app/clientes/<id>): abre por link (dá para abrir
   em outra aba), mostra compras, contato e campanhas, e as ações do lojista. */

const tenantId="a4ca9328-a916-4c64-943d-82dde3780001";
const participantId="dd539dec-8c4a-4dc6-a18f-d6eab4a62001";
const row={id:participantId,customer_reference:"",nuvemshop_customer_linked:true,phone_last4:"8888",
  manual_sales_count:2,manual_sales_reviewed:1,manual_sales_pending:1,manual_sales_reported_cents:219000,last_manual_sale_at:"2026-11-13T15:39:00Z",
  display_name:"Pessoa QA",contact_email:"qa@example.invalid",status:"active",consented_at:"2026-11-11T10:00:00Z",joined_at:"2026-11-11T10:00:00Z",
  consent_channel:"customer_portal",last_program_activity_at:null,points_balance:null,points_pending:null,points_status:"not_active",
  cashback_balance_cents:null,cashback_pending_cents:null,cashback_reserved_cents:null,balance_status:"not_implemented"};
const detail=(status="active")=>({participant:{...row,status},
  profile:{email_verified:true,marketing_opt_in:true,birth_day:12,birth_month:3,terms_version:"v1"},
  sales:[{id:"s1",channel:"counter",reference:"CUPOM-0042",amount_cents:150000,at:"2026-11-13T15:39:00Z",state:"awaiting_review",order_status:"paid"},
    {id:"s2",channel:"nuvemshop",reference:"14111",amount_cents:69000,at:"2026-11-12T10:00:00Z",state:"verified_manual",order_status:"paid"}],
  offers:[{id:"o1",goal:"reactivation",title:"Sentimos sua falta: +200 pontos",message:"Compre até 30/11 e ganhe 200 pontos extras.",bonus_points:200,multiplier:null,ends_on:"2026-11-30"}]});

async function mockPortal(page:Page,role="owner"){
  await page.context().addCookies([{name:"csrftoken",value:"client-csrf",url:"http://127.0.0.1:4173"}]);
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify({authenticated:true,user:{username:"qa",display_name:"QA"},
      tenants:[{id:tenantId,name:"Loja de teste",slug:"loja-test",status:"active",role}]})}));
  await page.route("**/api/v1/tenants/**/participants/**",r=>{
    const url=r.request().url();
    if(url.includes("/status/")){const s=r.request().postDataJSON().status;
      return r.fulfill({contentType:"application/json",body:JSON.stringify({...detail(s),points_credited:false,messages_sent:false})});}
    if(url.includes("/participants/"+participantId+"/"))return r.fulfill({contentType:"application/json",body:JSON.stringify(detail())});
    return r.fulfill({contentType:"application/json",body:JSON.stringify({source:"verified_opt_in_only",data_status:"consent_verified",
      summary:{total:1,active:1,paused:0},total_filtered:1,limit:20,offset:0,items:[row],note:""})});
  });
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",r=>r.fulfill({contentType:"application/json",
    body:JSON.stringify({configured:false,connected:false,store_id:null,scope:null,mode:"read_products_only",ready_for_write:false})}));
}

for(const width of [390,768,1440]){
  test("Cliente abre em página própria com compras, contato e ações em "+width+"px",async ({page},info)=>{
    await page.setViewportSize({width,height:900});
    await mockPortal(page);
    await page.goto("/app/clientes");
    const link=width<=760?page.getByRole("list",{name:"Participantes encontrados"}).getByRole("link",{name:/Pessoa QA/})
      :page.locator(".vf-clients-table").getByRole("link",{name:"Abrir Pessoa QA"});
    await expect(link).toHaveAttribute("href","/app/clientes/"+participantId);
    await link.click();
    await expect(page).toHaveURL(new RegExp("/app/clientes/"+participantId+"$"));
    await expect(page.getByRole("heading",{name:"Pessoa QA",level:1})).toBeVisible();
    await expect(page.getByText("Aniversário 12 mar")).toBeVisible();
    await expect(page.getByText("Celular final 8888")).toBeVisible();
    await expect(page.getByText("CUPOM-0042",{exact:false})).toBeVisible();
    await expect(page.getByRole("region",{name:"Campanhas para este cliente"}).getByText("Sentimos sua falta: +200 pontos")).toBeVisible();
    await expect(page.getByRole("button",{name:"1 para conferir"})).toBeVisible();
    expect(await page.getByRole("button",{name:/Resgatar|Usar cashback/}).count()).toBe(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({path:info.outputPath("client-page-"+width+".png"),fullPage:true});
    await page.goBack();
    await expect(page.getByRole("heading",{name:"Quem faz parte do clube"})).toBeVisible();
  });
}

test("Link direto abre o cliente; pausa pede confirmação e Registrar venda já traz o cliente",async ({page})=>{
  await page.setViewportSize({width:1440,height:900});
  await mockPortal(page);
  await page.route("**/api/v1/tenants/**/sales/manual/",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({items:[]})}));
  await page.goto("/app/clientes/"+participantId);
  await page.getByRole("button",{name:"Pausar participação"}).click();
  await page.getByRole("button",{name:"Confirmar pausa"}).click();
  await expect(page.getByText("Participação pausada. Novas compras não contam",{exact:false})).toBeVisible();
  await expect(page.locator(".vf-client-actions").getByRole("button",{name:"Registrar venda"})).toBeDisabled();
  await page.getByRole("button",{name:"Retomar participação"}).click();
  await expect(page.getByText("Participação retomada.")).toBeVisible();
  await page.locator(".vf-client-actions").getByRole("button",{name:"Registrar venda"}).click();
  await expect(page).toHaveURL(/\/app\/vendas$/);
  await expect(page.getByText("Pessoa QA").first()).toBeVisible();
});

test("Analista vê o cliente sem ações de gestão",async ({page})=>{
  await mockPortal(page,"analyst");
  await page.goto("/app/clientes/"+participantId);
  await expect(page.getByRole("heading",{name:"Pessoa QA",level:1})).toBeVisible();
  await expect(page.getByRole("button",{name:"Pausar participação"})).toHaveCount(0);
  await expect(page.locator(".vf-client-actions")).toHaveCount(0);
});
