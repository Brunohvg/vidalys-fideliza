import {expect,test,type Page} from "@playwright/test";

/* Página do cliente: mensagem pronta de WhatsApp com o saldo real. O sistema não envia nada
   e não guarda o celular completo: abre wa.me só com o texto. Dados sintéticos. */

const tenantId="b5db0439-a916-4c64-943d-82dde3780002";
const pid="ee649eed-8c4a-4dc6-a18f-d6eab4a62002";
const row={id:pid,customer_reference:"",nuvemshop_customer_linked:false,phone_last4:"4321",manual_sales_count:1,manual_sales_reviewed:1,
  manual_sales_pending:0,manual_sales_reported_cents:15000,last_manual_sale_at:"2026-11-13T15:39:00Z",display_name:"Carla Souza",
  contact_email:"carla@example.invalid",status:"active",consented_at:"2026-11-01T10:00:00Z",joined_at:"2026-11-01T10:00:00Z",
  consent_channel:"customer_portal",last_program_activity_at:null,points_balance:1500,points_pending:0,points_status:"ledger_only",
  cashback_balance_cents:null,cashback_pending_cents:null,cashback_reserved_cents:null,balance_status:"not_implemented"};
const gift={mode:"giftback",percent_bps:1000,cap_cents:2000,min_order_cents:8000,validity_days:30,hold_days:7};
const offer={id:"o1",goal:"reactivation",title:"Semana do clube",message:"Compre até 30/11 e ganhe o dobro de crédito",bonus_points:0,multiplier:2,ends_on:"2026-11-30"};
const json=(b:unknown)=>({contentType:"application/json",body:JSON.stringify(b)});

async function mock(page:Page,{marketing=true,giftback=true}={}){
  await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:true,user:{username:"qa",display_name:"QA"},
    tenants:[{id:tenantId,name:"Ateliê Aurora",slug:"atelie-aurora",status:"active",role:"owner"}]})));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill(json({participant:row,
    profile:{email_verified:true,marketing_opt_in:marketing,birth_day:null,birth_month:null,terms_version:"v1"},
    sales:[],offers:[offer],program:giftback?gift:{mode:"points"}})));
  await page.route("**/api/v1/tenants/**/sales/counter/participants/**/wallet/",r=>r.fulfill(json(giftback?
    {program:gift,credit:{available_cents:1500,min_order_cents:8000,in_site_coupon_cents:1500},pilot_active:true,available:0,pending:0,reserved:1500,
     next_expiry:"2026-12-05T12:00:00Z",rewards:[],next_reward:null}
    :{program:{mode:"points"},credit:null,pilot_active:true,available:1500,pending:0,reserved:0,next_expiry:"2026-12-20T12:00:00Z",
     rewards:[{id:"r1",title:"Vale R$ 10",points_cost:1000,discount_cents:1000,min_order_cents:5000,affordable:true,exhausted:false}],next_reward:null})));
}
const text=(page:Page)=>page.getByRole("textbox",{name:"Texto da mensagem"});
const noOverflow=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);

for(const width of [390,768,1440]){
  test("Mensagem pronta de crédito no giftback em "+width+"px",async({page},info)=>{
    await page.setViewportSize({width,height:900});await mock(page);await page.goto("/app/clientes/"+pid);
    await expect(page.getByRole("heading",{name:"Mensagem pronta"})).toBeVisible();
    await expect(text(page)).toHaveValue(/^Oi, Carla! Aqui é da loja Ateliê Aurora\. Você tem R\$\s15,00 de crédito para usar com a gente, até 05\/12\./);
    await expect(text(page)).toHaveValue(/a partir de R\$\s80,00: é só informar seu celular no caixa ou usar o cupom no site\./);
    await expect(text(page)).toHaveValue(/\/clube\/atelie-aurora$/);
    const open=page.getByRole("link",{name:"Abrir no WhatsApp"});
    const href=await open.getAttribute("href");
    expect(href).toMatch(/^https:\/\/wa\.me\/\?text=/);
    expect(decodeURIComponent(href!.split("text=")[1])).toContain("Você tem R$");
    await expect(page.getByText("escolha o contato com final 4321")).toBeVisible();
    await noOverflow(page);
    const card=page.locator(".vf-wa");await card.scrollIntoViewIfNeeded();
    await card.screenshot({path:info.outputPath("whatsapp-"+width+".png")});
  });
}

test("Campanha só para quem aceitou ofertas e texto editado vai para o link",async({page})=>{
  await page.setViewportSize({width:1440,height:900});await mock(page);await page.goto("/app/clientes/"+pid);
  await page.getByRole("radio",{name:"Campanha"}).click();
  await expect(text(page)).toHaveValue(/Semana do clube: Compre até 30\/11 e ganhe o dobro de crédito\./);
  await text(page).fill("Oi Carla, passa aqui hoje!");
  expect(await page.getByRole("link",{name:"Abrir no WhatsApp"}).getAttribute("href")).toBe("https://wa.me/?text="+encodeURIComponent("Oi Carla, passa aqui hoje!"));
  await page.getByRole("radio",{name:"Avisar crédito"}).click();
  await expect(text(page)).toHaveValue(/de crédito/);
});

test("Sem aceite de ofertas não mostra campanha; pontos sugere o vale que dá para trocar",async({page})=>{
  await page.setViewportSize({width:390,height:844});await mock(page,{marketing:false,giftback:false});await page.goto("/app/clientes/"+pid);
  await expect(page.getByRole("radio",{name:"Campanha"})).toHaveCount(0);
  await expect(page.getByText("não aceitou ofertas")).toBeVisible();
  await expect(text(page)).toHaveValue(/Você tem 1\.500 pontos e já pode trocar por Vale R\$ 10 \(R\$\s10,00 de desconto\) na próxima compra, até 20\/12\./);
  await page.getByRole("radio",{name:"Lembrar do clube"}).click();
  await expect(text(page)).toHaveValue(/junta pontos que viram desconto/);
});
