import {expect,test,type Page} from "@playwright/test";

const tenant={
  id:"7c0e36ab-4a58-4e0b-9d65-cc4a0db90a26",
  name:"Loja Exemplo",slug:"loja-exemplo",status:"active",role:"owner",
};

async function setup(page:Page,role:"owner"|"analyst"="owner"){
  await page.context().addCookies([{
    name:"csrftoken",value:"csrf-settings-qa",domain:"127.0.0.1",path:"/"
  }]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      authenticated:true,
      user:{username:"merchant-settings",display_name:"Lojista QA"},
      tenants:[{...tenant,role}],
    })
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:true,connected:true,store_id:"PRIVATE-123",
      scope:"read_customers,read_products",mode:"read_products_only",
      ready_for_write:false,
      customer_matching:{
        preview_enabled:false,customer_scope_granted:true,
        read_only_preview_available:false,
        requires_partner_portal_scope_and_reinstallation:false,
        will_activate_participants:false,will_credit_cashback:false,
      }
    })
  }));
  await page.route("**/api/v1/tenants/**/privacy/requests/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      pending_total:1,access_requests:1,deletion_requests:0,
      items:[{
        id:"a9d97a5e-4840-4f68-b65a-90f0623a5f12",
        type:"data_access",received_at:"2026-11-11T10:00:00Z",status:"em_analise",
        report_available:true,downloaded:false,can_confirm:false,
      }],
      note:"Solicitação em análise",
    }),
  }));
  await page.route("**/api/v1/tenants/**/settings/",async route=>{
    const url=route.request().url();
    expect(url).toContain(tenant.id);
    if(route.request().method()==="PATCH"){
      const payload=route.request().postDataJSON();
      expect(route.request().headers()["x-csrftoken"]).toBe("csrf-settings-qa");
      expect(payload.expected_version).toBe(0);
      expect(payload.program_name).toBe("Clube Minha Loja");
      await route.fulfill({
        contentType:"application/json",body:JSON.stringify({
          version:1,updated:true,branding:{
            program_name:payload.program_name,
            primary_color:payload.primary_color,
            accent_color:payload.accent_color,
            support_email:payload.support_email,
          }
        })
      });
    }else{
      await route.fulfill({
        contentType:"application/json",body:JSON.stringify({
          tenant_id:tenant.id,tenant_name:tenant.name,
          tenant_slug:tenant.slug,tenant_status:"active",
          can_edit:role==="owner",version:0,public_link:null,
          branding:{
            program_name:"Clube Exemplo",
            primary_color:"#087F79",accent_color:"#37D5BB",
            support_email:"contato@example.invalid",
          },
          features:{
            public_signup_enabled:false,
            email_delivery_enabled:false,
            customer_preview_enabled:false,
            cashback_activation_enabled:false,
            custom_domain_available:false,
          },
          note:"Informações operacionais somente para uso interno."
        })
      });
    }
  });
}

async function goSettings(page:Page,width:number){
  await page.goto("/");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.getByRole("button",{name:"Configurações"}).click();
  await expect(page.getByRole("heading",{name:"Configurações"})).toBeVisible();
}

for(const width of [390,768,1440]){
  test("Lojista vê preferências, não diagnósticos técnicos em "+width+"px",async ({page})=>{
    await page.setViewportSize({width,height:880});
    await setup(page);
    await goSettings(page,width);
    await expect(page.getByRole("heading",{name:"Aparência do programa"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Conexão com a loja"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Regras do clube"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Página do clube"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Privacidade dos participantes"})).toBeVisible();
    await expect(page.getByText("Solicitações em análise")).toBeVisible();
    await expect(page.getByText("Pedido de acesso aos dados")).toBeVisible();
    await expect(page.getByText("Clube Exemplo",{exact:true})).toBeVisible();
    await expect(page.getByText("Nuvemshop",{exact:true})).toBeVisible();
    await expect(page.getByText("Autorização registrada",{exact:true})).toBeVisible();
    await expect(page.getByText("Conectada",{exact:true})).toHaveCount(0);
    const main=page.locator(".portal-content");
    const text=await main.innerText();
    for(const forbidden of [
      "read_customers","SMTP2GO","OAuth","token instalado",
      "PRIVATE-123","Identificador da loja","Variável de ambiente",
      "Ambiente do servidor","Versão 0","fideliza.sualoja.com.br",
      "DNS","SSL",
    ]){
      expect(text,forbidden+" não deve aparecer ao lojista").not.toContain(forbidden);
    }
    const overflow=await page.evaluate(()=>
      document.documentElement.scrollWidth-window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test("Proprietário salva nome do clube, sem acionar mudanças na Nuvemshop",async ({page})=>{
  await setup(page);
  let patchCount=0;
  await page.route("**/api/v1/tenants/**/settings/",async (route)=>{
    // O primeiro mock atende a requisição; este contador observa somente PATCH.
    if(route.request().method()==="PATCH")patchCount++;
    await route.fallback();
  });
  await goSettings(page,1440);
  await page.getByPlaceholder("Clube Loja Exemplo").fill("Clube Minha Loja");
  await page.getByRole("button",{name:"Salvar alterações"}).click();
  await expect(page.getByText("Alterações salvas.",{exact:false})).toBeVisible();
  await expect(page.getByText("Clube Minha Loja",{exact:true})).toBeVisible();
  expect(patchCount).toBe(1);
});

test("Analista consulta aparência mas não vê ação de salvar",async ({page})=>{
  await setup(page,"analyst");
  await goSettings(page,1440);
  await expect(page.getByText("Um administrador da loja pode alterá-las.",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:"Salvar alterações"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Atualizar conexão"})).toHaveCount(0);
});

test("Relatório de dados exige download e confirmação explícita, sem segredo na tela",async ({page})=>{
  await setup(page);
  const receiptId="a9d97a5e-4840-4f68-b65a-90f0623a5f12";
  const digest="a".repeat(64);
  let downloaded=0,confirmed=0;
  await page.route("**/privacy/requests/**/report/",route=>{
    downloaded++;
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-csrftoken"]).toBe("csrf-settings-qa");
    expect(route.request().url()).toContain(receiptId);
    return route.fulfill({
      contentType:"application/json",
      headers:{
        "X-Fideliza-Report-Digest":digest,
        "X-Fideliza-Report-Complete":"true",
      },
      body:JSON.stringify({documento:"Relatório da loja",aceites:[]}),
    });
  });
  await page.route("**/privacy/requests/**/confirm/",route=>{
    confirmed++;
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-csrftoken"]).toBe("csrf-settings-qa");
    expect(route.request().postDataJSON()).toEqual({confirm:true,digest});
    return route.fulfill({
      contentType:"application/json",
      body:JSON.stringify({status:"completed",message:"Recebimento do relatório confirmado e registrado."}),
    });
  });
  await goSettings(page,1440);
  await expect(page.getByRole("button",{name:"Confirmar que recebi"})).toHaveCount(0);
  const downloadPromise=page.waitForEvent("download");
  await page.getByRole("button",{name:"Baixar relatório"}).click();
  const file=await downloadPromise;
  expect(file.suggestedFilename()).toContain("relatorio-fideliza");
  expect(downloaded).toBe(1);
  expect(confirmed).toBe(0);
  await expect(page.getByRole("button",{name:"Confirmar que recebi"})).toBeVisible();
  await page.getByRole("button",{name:"Confirmar que recebi"}).click();
  await expect(page.getByText("Recebimento do relatório confirmado e registrado.")).toBeVisible();
  expect(confirmed).toBe(1);
  await expect(page.getByRole("button",{name:"Baixar relatório"})).toHaveCount(0);
  await expect(page.getByText("Nenhuma solicitação pendente",{exact:false})).toHaveCount(0);
});
