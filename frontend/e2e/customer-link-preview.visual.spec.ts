import {test,expect,type Page} from "@playwright/test";

const store={id:"97f0f78d-24be-454e-9609-90773a7d4fc1",
  name:"Loja vínculo QA",slug:"loja-vinculo-qa",status:"active",role:"owner"};
const receiptId="6ad93a13-4113-487b-bfd6-2b2e17856bd7";

async function mock(page:Page,canPreview:boolean){
  await page.context().addCookies([{
    name:"csrftoken",value:"csrf-customer-preview-qa",
    url:"http://127.0.0.1:4173",
  }]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      authenticated:true,user:{username:"admin-qa",display_name:"Administrador QA"},
      tenants:[store],
    }),
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:0,active:0,paused:0},total_filtered:0,limit:20,
      offset:0,items:[],note:"Nenhum participante ativo",
    }),
  }));
  await page.route("**/api/v1/tenants/**/campaign-drafts/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      mode:"draft_only",activation_available:false,items:[],
    }),
  }));
  await page.route("**/api/v1/tenants/**/program-terms/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      mode:"approval_required",public_signup_enabled:false,
      terms:{id:"29a14cf9-11bb-4fb0-8490-4d7d52b0202e",version:"v1",
        title:"Regulamento de teste",body:"Termos só para teste.",
        privacy_notice:"Aviso de privacidade de teste.",
        approved_at:"2026-11-11T10:00:00Z"},
    }),
  }));
  await page.route("**/api/v1/tenants/**/enrollment-submissions/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      mode:"consents_pending_identity_verification",total:2,note:"Nenhum crédito ativo.",
      items:[
        {id:receiptId,name:"Cliente Verificado",email:"verificado@example.invalid",
          terms_version:"v1",accepted_at:"2026-11-11T11:00:00Z",
          marketing_opt_in:false,status:"email_verified"},
        {id:"1ca6f207-32f0-4617-a7f9-b0da59dff23e",
          name:"Cliente Pendente",email:"pendente@example.invalid",
          terms_version:"v1",accepted_at:"2026-11-11T11:02:00Z",
          marketing_opt_in:false,status:"pending_verification"},
      ],
    }),
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:true,connected:true,store_id:"1234",
      scope:canPreview?"read_customers,read_products":"read_products",
      mode:"read_products_only",ready_for_write:false,
      customer_matching:{
        preview_enabled:canPreview,customer_scope_granted:canPreview,
        read_only_preview_available:canPreview,
        requires_partner_portal_scope_and_reinstallation:!canPreview,
        will_activate_participants:false,will_credit_cashback:false,
      },
    }),
  }));
}

for(const width of [390,1440]){
  test("Lojista confere somente cliente com e-mail verificado em "+width+"px",
    async ({page})=>{
      await page.setViewportSize({width,height:900});
      await mock(page,true);
      let requests=0;
      await page.route("**/customer-match/preview/",async route=>{
        requests+=1;
        expect(route.request().method()).toBe("POST");
        expect(route.request().postDataJSON()).toEqual({});
        expect(route.request().url()).toContain(receiptId);
        expect(route.request().headers()["x-csrftoken"]).toBe("csrf-customer-preview-qa");
        await route.fulfill({contentType:"application/json",body:JSON.stringify({
          mode:"read_only_customer_match_preview",status:"one_exact_match",
          customer_id:"123",email_verified:true,
          submission_id:receiptId,tenant_id:store.id,
          scope_required:"read_customers",writes_performed:0,
          participant_created:false,cashback_enabled:false,
          note:"Prévia não cria vínculo nem prova compra.",
        })});
      });
      await page.goto("/");
      if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
      await page.locator(".portal-nav").getByRole("button",{name:/^Programa/}).click();
      await page.getByRole("navigation",{name:"Áreas do programa"}).getByRole("button",{name:"Participantes"}).click();
      await page.getByRole("tab",{name:/Solicitações/}).click();
      await expect(page.getByText("Cliente Verificado")).toBeVisible();
      await expect(page.getByText("Cliente Pendente")).toBeVisible();
      await expect(page.getByRole("button",{name:"Conferir cadastro na Nuvemshop"})).toHaveCount(1);
      await page.getByRole("button",{name:"Conferir cadastro na Nuvemshop"}).click();
      await expect(page.getByText("Encontramos um cadastro correspondente ao e-mail confirmado.")).toBeVisible();
      expect(requests).toBe(1);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
        .toBeLessThanOrEqual(1);
    });
}

test("Sem autorização read_customers, não consultar clientes da loja",async ({page})=>{
  await mock(page,false);
  await page.goto("/");
  await page.locator(".portal-nav").getByRole("button",{name:/^Programa/}).click();
      await page.getByRole("navigation",{name:"Áreas do programa"}).getByRole("button",{name:"Participantes"}).click();
      await page.getByRole("tab",{name:/Solicitações/}).click();
  await expect(page.getByText("Ainda não é possível conferir cadastros de clientes.",{exact:false}))
    .toBeVisible();
  await expect(page.getByText("read_customers",{exact:false})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Conferir cadastro na Nuvemshop"})).toHaveCount(0);
});

test("Lojista aprova explicitamente vínculo verificado sem conceder recompensas",async ({page})=>{
  await mock(page,true);
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:true,connected:true,store_id:"1234",
      scope:"read_customers,read_products,read_orders",
      mode:"read_products_only",ready_for_write:false,
      customer_matching:{
        preview_enabled:true,customer_scope_granted:true,
        read_only_preview_available:true,participant_approval_available:true,
        requires_partner_portal_scope_and_reinstallation:false,
        will_activate_participants:false,will_credit_cashback:false,
      },
    }),
  }));
  await page.route("**/customer-match/preview/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      mode:"read_only_customer_match_preview",status:"one_exact_match",
      customer_id:"123",email_verified:true,submission_id:receiptId,tenant_id:store.id,
      scope_required:"read_customers",writes_performed:0,
      participant_created:false,cashback_enabled:false,
      note:"Prévia sem alterações",
    }),
  }));
  let approvals=0;
  await page.route("**/customer-match/approve/",async route=>{
    approvals+=1;
    expect(route.request().postDataJSON()).toEqual({
      customer_id:"123",confirm:true,
    });
    expect(route.request().url()).toContain(receiptId);
    await route.fulfill({
      status:201,contentType:"application/json",body:JSON.stringify({
        status:"linked",already_linked:false,participant_id:"7cc50f6a-4cda-4166-9bf8-90de14040bc8",
        cashback_enabled:false,orders_modified:false,
        message:"Cliente vinculado ao programa. Recompensas ainda não estão disponíveis.",
      }),
    });
  });
  await page.goto("/");
  await page.locator(".portal-nav").getByRole("button",{name:/^Programa/}).click();
      await page.getByRole("navigation",{name:"Áreas do programa"}).getByRole("button",{name:"Participantes"}).click();
      await page.getByRole("tab",{name:/Solicitações/}).click();
  await page.getByRole("button",{name:"Conferir cadastro na Nuvemshop"}).click();
  await page.getByRole("button",{name:"Aprovar participação"}).click();
  await expect(page.getByText("Confirmar a adesão deste cliente ao clube?")).toBeVisible();
  expect(approvals).toBe(0);
  await page.getByRole("button",{name:"Sim, aprovar participação"}).click();
  await expect(page.getByText("Cliente vinculado ao programa.",{exact:false})).toBeVisible();
  await expect(page.getByText("Cliente Verificado")).toHaveCount(0);
  expect(approvals).toBe(1);
  await expect(page.getByText("Recompensas ainda não estão disponíveis.",{exact:false})).toBeVisible();
});
