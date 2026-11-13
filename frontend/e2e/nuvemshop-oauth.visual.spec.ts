import { expect, test, type Page } from "@playwright/test";

const tenant = {
  id: "49d82906-83be-4b1b-862b-a65103c53211",
  name: "Loja piloto fictícia",
  slug: "piloto-ficticio",
  status: "draft",
  role: "owner"
};

async function session(page: Page, role: "owner" | "analyst" = "owner") {
  await page.context().addCookies([{
    name: "csrftoken", value: "csrf-synthetic-only",
    domain: "127.0.0.1", path: "/"
  }]);
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      authenticated: true,
      user: { username: "oauth-qa", display_name: "Conta de teste" },
      tenants: [{ ...tenant, role }]
    })
  }));
}

async function go(page: Page, width: number) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
  if (width <= 1020) await page.getByRole("button", { name: "Abrir menu" }).click();
  await page.locator(".portal-nav").getByRole("button", { name: /Conciliação/ }).click();
  await expect(page.getByRole("heading", { name: "Consulte produtos da sua Nuvemshop" })).toBeVisible();
}

const livePreview = {
  mode: "read_only_snapshot_preview",
  source: "nuvemshop_live_read_only",
  page: 1, empty: false,
  automatically_approved: false, writes_performed: 0,
  summary: {
    products: 1, variants: 1, matched: 0, review_required: 1,
    unmapped: 0, missing_api_cost: 1, missing_sku: 0
  },
  items: [{
    product_id: "30001", product_name: "Linha de demonstração",
    variant_id: "30002", sku: "LINHA-TESTE", barcode: "0780000000123",
    price_cents: 1990, promotional_price_cents: null, api_cost_cents: null,
    local_cost_cents: 1200, local_verified: true, local_reference: "REF-TESTE",
    local_item_id: "local-01", match_type: "variant_id", decision: "review_required",
    issues: ["price_differs_from_local"], will_modify_cost: false,
    will_modify_product: false
  }],
  warnings: ["Nenhuma gravação."]
};

for (const width of [390, 768, 1440]) {
  test("OAuth conectado e catálogo somente leitura em " + width + "px", async ({ page }, testInfo) => {
    await page.setViewportSize({width, height: width === 390 ? 844 : 900});
    await session(page);
    await page.route("**/api/v1/tenants/**/nuvemshop/status/", route => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        configured: true, connected: true, store_id: "54321",
        scope: "read_products", mode: "read_products_only", ready_for_write: false
      })
    }));
    let reads = 0;
    await page.route("**/api/v1/tenants/**/nuvemshop/catalog/preview/**", route => {
      reads++;
      expect(route.request().method()).toBe("GET");
      expect(route.request().url()).toContain(tenant.id);
      expect(route.request().headers()["authorization"]).toBeUndefined();
      return route.fulfill({contentType: "application/json", body: JSON.stringify(livePreview)});
    });
    await go(page, width);
    await expect(page.getByText("Autorizada", {exact:true})).toBeVisible();
    await expect(page.locator(".nuv-connection")).toContainText("validade atual do acesso");
    await expect(page.locator(".nuv-connection")).not.toContainText("54321");
    await expect(page.locator(".nuv-connection")).not.toContainText("read_products");
    await expect(page.getByRole("button", {name:"Autorizar minha loja"})).toHaveCount(0);
    await page.getByRole("button", {name:"Consultar 3 produtos"}).click();
    await expect(page.getByText("Prévia oficial carregada.")).toBeVisible();
    await expect(page.getByText("Linha de demonstração")).toBeVisible();
    await expect(page.getByText("Preço divergente")).toBeVisible();
    expect(reads).toBe(1);
    const geometry=await page.evaluate(()=>({
      width:window.innerWidth, scroll:document.documentElement.scrollWidth
    }));
    expect(geometry.scroll,JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.width+1);
    await page.evaluate(()=>window.scrollTo(0,0));
    await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(0);
    await page.screenshot({
      path:testInfo.outputPath("nuvemshop-connected-"+width+".png"),fullPage:true
    });
  });
}

test("visão geral encaminha Nuvemshop sem conexão para Configurações", async ({page})=>{
  await session(page);
  await page.route("**/api/v1/tenants/**/nuvemshop/status/", route=>route.fulfill({
    contentType:"application/json", body:JSON.stringify({
      configured:true, connected:false, store_id:null, scope:null,
      mode:"read_products_only",ready_for_write:false,
      connection_check:{next_step:"authorize_store",live_access_checked:false},
    }),
  }));
  await page.route("**/api/v1/tenants/**/settings/", route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      tenant_id:tenant.id,tenant_name:tenant.name,tenant_slug:tenant.slug,
      tenant_status:"active",can_edit:true,version:0,public_link:null,
      branding:{program_name:"Clube Piloto",primary_color:"#087F79",
        accent_color:"#37D5BB",support_email:"teste@example.invalid"},
      features:{public_signup_enabled:false,email_delivery_enabled:false,
        customer_preview_enabled:false,cashback_activation_enabled:false,
        custom_domain_available:false},
    }),
  }));
  await page.goto("/");
  await page.getByRole("button",{name:"Conectar canal"}).click();
  await expect(page.getByRole("heading",{name:"Configurações"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Conexão com a loja"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Conectar minha loja"})).toBeVisible();
});

test("autorização OAuth não é rotulada como acesso verificado no início",async ({page})=>{
  await session(page);
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:true,connected:true,store_id:"42123",scope:"read_products",
      mode:"read_products_only",ready_for_write:false,
      connection_check:{next_step:"verify_catalog_with_live_get",
        catalog_scope_granted:true,live_access_checked:false},
    }),
  }));
  await page.goto("/");
  await expect(page.getByText("Autorizada; verificar",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Verificar conexão"})).toBeVisible();
  await expect(page.getByText("Autorização registrada não prova que o token continua válido.")).toBeVisible();
});

test("OAuth não configurado impede conexão sem enviar segredos", async ({page})=>{
  await session(page);
  await page.route("**/api/v1/tenants/**/nuvemshop/status/", route => route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      configured:false,connected:false,store_id:null,scope:null,
      mode:"read_products_only",ready_for_write:false
    })
  }));
  await page.route("**/api/v1/tenants/**/settings/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      tenant_id:tenant.id,tenant_name:tenant.name,tenant_slug:tenant.slug,
      tenant_status:"active",can_edit:true,version:0,public_link:null,
      branding:{program_name:"Clube Piloto",primary_color:"#087F79",
        accent_color:"#37D5BB",support_email:"teste@example.invalid"},
      features:{public_signup_enabled:false,email_delivery_enabled:false,
        customer_preview_enabled:false,cashback_activation_enabled:false,
        custom_domain_available:false},
    }),
  }));
  await go(page,1440);
  await expect(page.getByRole("button",{name:/Autorizar minha loja/})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Ver conexão em Configurações"})).toBeVisible();
  await page.getByRole("button",{name:"Ver conexão em Configurações"}).click();
  await expect(page.getByRole("heading",{name:"Configurações"})).toBeVisible();
});

test("Analista não pode começar OAuth", async ({page})=>{
  await session(page,"analyst");
  await page.route("**/api/v1/tenants/**/nuvemshop/status/", route => route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      configured:true,connected:false,store_id:null,scope:null,
      mode:"read_products_only",ready_for_write:false
    })
  }));
  await go(page,1440);
  await expect(page.getByRole("button",{name:/Autorizar minha loja/})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Ver conexão em Configurações"})).toBeVisible();
});

test("Retorno do OAuth não exibe code ou token", async ({page})=>{
  await session(page);
  await page.route("**/api/v1/tenants/**/nuvemshop/status/", route => route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      configured:true,connected:true,store_id:"54321",scope:"read_products",
      mode:"read_products_only",ready_for_write:false
    })
  }));
  await page.route("**/api/v1/tenants/**/settings/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      tenant_id:tenant.id,tenant_name:tenant.name,tenant_slug:tenant.slug,
      tenant_status:"active",can_edit:true,version:0,public_link:null,
      branding:{program_name:"Clube Piloto",primary_color:"#087F79",
        accent_color:"#37D5BB",support_email:"teste@example.invalid"},
      features:{public_signup_enabled:false,email_delivery_enabled:false,
        customer_preview_enabled:false,cashback_activation_enabled:false,
        custom_domain_available:false},
    }),
  }));
  await page.goto("/?nuvemshop=connected&nuvemshop_tenant="+tenant.id);
  await expect(page.getByRole("heading",{name:"Configurações"})).toBeVisible();
  await expect(page.getByText("Autorização registrada.",{exact:false})).toBeVisible();
  await expect(page).toHaveURL("http://127.0.0.1:4173/");
  await expect(page.locator("body")).not.toContainText("access_token");
});
