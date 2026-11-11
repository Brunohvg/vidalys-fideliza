import { expect, test, type Page } from "@playwright/test";

const store = {
  id: "f9eb2207-1679-482b-b72e-87c4106bc50e",
  name: "Laboratório sintético",
  slug: "lab-sintetico",
  status: "draft",
  role: "analyst"
};

async function init(page: Page) {
  await page.context().addCookies([{
    name: "csrftoken", value: "csrf-json-preview", domain: "127.0.0.1", path: "/"
  }]);
  await page.route("**/api/v1/tenants/**/nuvemshop/status/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ configured: false, connected: false, store_id: null,
      scope: null, mode: "read_products_only", ready_for_write: false })
  }));
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      authenticated: true, user: { username: "analyst-qa", display_name: "Analista QA" },
      tenants: [store]
    })
  }));
}

async function navigate(page: Page, width: number) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
  if (width <= 1020) await page.getByRole("button", { name: "Abrir menu" }).click();
  await page.locator(".portal-nav").getByRole("button", { name: /Conciliação/ }).click();
  if (width <= 1020) {
    await expect.poll(() => page.locator(".portal-side").evaluate(
      el => el.getBoundingClientRect().right
    )).toBeLessThan(2);
  }
  await expect(page.getByRole("heading", { name: "Prévia JSON de produtos" })).toBeVisible();
}

const response = {
  mode: "read_only_snapshot_preview",
  source: "operator_supplied_json",
  automatically_approved: false,
  writes_performed: 0,
  summary: {
    products: 2, variants: 3, matched: 1, review_required: 1,
    unmapped: 1, missing_api_cost: 2, missing_sku: 0
  },
  items: [
    {
      product_id: "89101", product_name: "Fita cetim 10 mm — demonstração",
      variant_id: "99301", sku: "FITA-10-VERMELHA",
      barcode: "0780000000123", price_cents: 1490, promotional_price_cents: 1290,
      api_cost_cents: null, decision: "unmapped", match_type: "none",
      local_item_id: null, local_reference: null, local_cost_cents: null,
      local_verified: false, issues: [], will_modify_cost: false, will_modify_product: false
    },
    {
      product_id: "89101", product_name: "Fita cetim 10 mm — demonstração",
      variant_id: "99302", sku: "FITA-10-AZUL",
      barcode: "0780000000456", price_cents: 1490, promotional_price_cents: null,
      api_cost_cents: 650, decision: "review_required", match_type: "sku_candidate",
      local_item_id: "local-cost-001", local_reference: "FITA-AZUL", local_cost_cents: 700,
      local_verified: true, issues: ["variant_id_changed"], will_modify_cost: false, will_modify_product: false
    },
    {
      product_id: "89102", product_name: "Argola 100 mm — demonstração",
      variant_id: "99303", sku: "ARG-100-TR", barcode: "",
      price_cents: 2990, promotional_price_cents: null,
      api_cost_cents: null, decision: "matched", match_type: "variant_id",
      local_item_id: "local-cost-002", local_reference: "ARG-100", local_cost_cents: 1400,
      local_verified: true, issues: [], will_modify_cost: false, will_modify_product: false
    }
  ],
  warnings: ["Somente uma amostra sintética."]
};

for (const width of [390, 768, 1440]) {
  test("Conciliação sem escrita e interface responsiva em "+width+"px", async ({ page }, testInfo) => {
    await page.setViewportSize({width, height: width===390?844:900});
    await init(page);
    let count=0;
    await page.route("**/api/v1/tenants/**/catalog/reconcile-preview/", async route=>{
      count++;
      const request = route.request();
      expect(request.method()).toBe("POST");
      expect(request.url()).toContain(store.id);
      expect(request.headers()["x-csrftoken"]).toBe("csrf-json-preview");
      const data=request.postDataJSON();
      expect(Object.keys(data)).toEqual(["products"]);
      expect(data.products).toHaveLength(2);
      expect(data.products[0].variants).toHaveLength(2);
      expect(data.products[0].variants[0].barcode).toBe("0780000000123");
      expect(data.products[0].variants[0]).not.toHaveProperty("description");
      await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(response)});
    });
    await navigate(page,width);
    await expect(page.getByText("Pronto para comparar")).toBeVisible();
    await page.getByRole("button",{name:"Usar exemplo fictício"}).click();
    await expect(page.getByText("Exemplo ilustrativo — não contém produtos reais")).toBeVisible();
    await page.getByRole("button",{name:"Analisar variantes"}).click();
    await expect(page.getByText("Análise concluída, nenhuma alteração realizada.")).toBeVisible();
    await expect(page.getByText("2 variante(s) sem custo na amostra.")).toBeVisible();
    await expect(page.locator(".reconcile-table tbody tr")).toHaveCount(3);
    expect(count).toBe(1);

    const dims=await page.evaluate(()=>({doc:document.documentElement.scrollWidth,viewport:window.innerWidth}));
    expect(dims.doc,JSON.stringify(dims)).toBeLessThanOrEqual(dims.viewport+1);

    await page.evaluate(()=>window.scrollTo(0,0));
    await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(0);
    await page.screenshot({path:testInfo.outputPath("catalog-preview-"+width+".png"),fullPage:true});

    await page.getByRole("button",{name:"Revisar",exact:true}).click();
    await expect(page.locator(".reconcile-table tbody tr")).toHaveCount(1);
    await expect(page.getByText("Possível troca de ID da variante")).toBeVisible();
    await page.getByRole("button",{name:"Correspondentes",exact:true}).click();
    await expect(page.locator(".reconcile-table tbody tr")).toHaveCount(1);
    await page.getByRole("button",{name:"Limpar"}).click();
    await expect(page.getByText("Pronto para comparar")).toBeVisible();
  });
}

test("JSON inválido bloqueia envio antes da API", async ({page})=>{
  await init(page);
  let calls=0;
  await page.route("**/api/v1/tenants/**/catalog/reconcile-preview/", async route=>{
    calls++;await route.fulfill({status:500,body:"unexpected"});
  });
  await navigate(page,1440);
  await page.getByLabel("Ou cole o JSON de uma amostra autorizada").fill("{invalid");
  await page.getByRole("button",{name:"Analisar variantes"}).click();
  await expect(page.locator(".reconcile-input-card").getByRole("alert")).toContainText("não é um JSON válido");
  expect(calls).toBe(0);
});
