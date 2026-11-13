import {expect, test, type Page} from "@playwright/test";

const tenantId="a4ca9328-a916-4c64-943d-82dde3780001";
const participantId="dd539dec-8c4a-4dc6-a18f-d6eab4a62001";

async function mockPortal(page:Page){
  await page.route("**/api/v1/auth/session/",r=>r.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:true,user:{username:"qa",display_name:"QA"},
      tenants:[{id:tenantId,name:"Loja de teste",slug:"loja-test",status:"draft",role:"owner"}]})
  }));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:1,active:1,paused:0},total_filtered:1,limit:20,offset:0,
      items:[{
        id:participantId,customer_reference:"ref-1",display_name:"Pessoa QA",
        contact_email:"qa@example.invalid",status:"active",
        consented_at:"2026-11-11T10:00:00Z",joined_at:"2026-11-11T10:00:00Z",
        consent_channel:"customer_portal",last_program_activity_at:null,
        points_balance:null,cashback_balance_cents:320,
        cashback_pending_cents:100,cashback_reserved_cents:0,
        balance_status:"ledger_only"
      }],
      note:"Adesão fictícia de teste"
    })
  }));
  await page.route("**/api/v1/tenants/**/participants/**/wallet/",r=>r.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      mode:"ledger_read_only",balance_status:"ledger_only",
      balances:{pending_cents:100,available_cents:320,reserved_cents:0},
      events:[{id:"8b41ff32-faa3-465c-a2bd-782a55abde0e",kind:"release",
        amount_cents:320,rule_version:"test-v1",created_at:"2026-11-11T10:00:00Z"}],
      events_limit:20,redemption_enabled:false,note:"Apenas testes."
    })
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",r=>r.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:false,connected:false,store_id:null,scope:null,
      mode:"read_products_only",ready_for_write:false
    })
  }));
}

for(const width of [390,768,1440]){
  test("Extrato visível, sem resgate, em "+width+"px",async ({page},info)=>{
    await page.setViewportSize({width,height:850});
    await mockPortal(page);
    await page.goto("/");
    if(width<=1020) await page.getByRole("button",{name:"Abrir menu"}).click();
    await page.getByRole("complementary",{name:"Menu do lojista"}).getByRole("button",{name:"Clientes",exact:true}).click();
    if(width<=1020){
      const list=page.getByRole("list",{name:"Participantes encontrados"});
      await expect(list.getByText("Pessoa QA")).toBeVisible();
      await list.getByText("Dados internos de teste").click();
      await list.getByRole("button",{name:"Ver extrato técnico"}).click();
    }else{
      const table=page.locator(".xp-table");
      await expect(table.getByText("Pessoa QA")).toBeVisible();
      await table.getByText("Registros internos de teste").click();
      await table.getByRole("button",{name:"Ver extrato técnico"}).click();
    }
    await expect(page.getByRole("heading",{name:"Histórico de Pessoa QA"})).toBeVisible();
    await expect(page.getByText("Pendente",{exact:true})).toBeVisible();
    await expect(page.getByText("Resgate desativado.",{exact:false})).toBeVisible();
    expect(await page.getByRole("button",{name:/Resgatar|Usar cashback/}).count()).toBe(0);
    const geometry=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
    expect(geometry).toBeLessThanOrEqual(1);
    await page.screenshot({path:info.outputPath("ledger-read-only-"+width+".png"),fullPage:true});
  });
}
