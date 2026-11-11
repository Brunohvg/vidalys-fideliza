import { expect, test, type Page } from "@playwright/test";

const tenant = {
  id: "c3c01152-6533-4dab-a99f-93d4a0123478",
  name: "Loja laboratório",
  slug: "laboratorio",
  status: "draft",
  role: "owner"
} as const;

type Record = {
  id: string; reference: string; name: string; sku: string; external_variant_id: string;
  unit_cost_cents: number | null; selling_price_cents: number | null;
  provenance: string; verified_at: string | null; verified_by_name: string | null;
  version: number; review_status: "missing_cost" | "needs_review" | "missing_price" | "ready_for_simulation";
  created_at: string; updated_at: string;
};

function status(item: Record): Record["review_status"] {
  if (item.unit_cost_cents === null) return "missing_cost";
  if (!item.verified_at) return "needs_review";
  if (item.selling_price_cents === null) return "missing_price";
  return "ready_for_simulation";
}

async function mockSession(page: Page, role: "owner" | "analyst" = "owner") {
  await page.context().addCookies([{
    name: "csrftoken", value: "csrf-costs-test", domain: "127.0.0.1", path: "/"
  }]);
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      authenticated: true, user: { username: "cost-merchant", display_name: "Lojista piloto" },
      tenants: [{ ...tenant, role }]
    })
  }));
}

async function navigateCosts(page: Page, width: number) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
  if (width <= 1020) await page.getByRole("button", { name: "Abrir menu" }).click();
  await page.locator(".portal-nav").getByRole("button", { name: /Custos por SKU/ }).click();
  if (width <= 1020) {
    await expect.poll(() => page.locator(".portal-side").evaluate(el => el.getBoundingClientRect().right)).toBeLessThan(2);
  }
  await expect(page.getByRole("heading", { name: "Custos e variantes" })).toBeVisible();
}

function mockCosts(page: Page, items: Record[], tracking: { writes: number }) {
  return page.route("**/api/v1/tenants/**/cost-items/**", async route => {
    const req = route.request();
    const url = new URL(req.url());
    expect(url.pathname).toContain(tenant.id);
    const isList = url.pathname.endsWith("/cost-items/");
    let response: unknown;
    let responseStatus = 200;

    if (req.method() === "GET" && isList) {
      const filter = url.searchParams.get("status");
      const q = (url.searchParams.get("q") || "").toLowerCase();
      const visible = items.filter(i => (!filter || i.review_status === filter) &&
        (!q || i.name.toLowerCase().includes(q) || i.reference.toLowerCase().includes(q) || i.sku.toLowerCase().includes(q)));
      const summary = {
        total: items.length,
        missing_cost: items.filter(i => i.review_status === "missing_cost").length,
        needs_review: items.filter(i => i.review_status === "needs_review").length,
        missing_price: items.filter(i => i.review_status === "missing_price").length,
        ready: items.filter(i => i.review_status === "ready_for_simulation").length
      };
      response = { summary, items: visible, total_filtered: visible.length, limit: 30, offset: 0, data_status: "manual_only" };
    } else if (req.method() === "POST" && isList) {
      tracking.writes++;
      expect(req.headers()["x-csrftoken"]).toBe("csrf-costs-test");
      const data = req.postDataJSON();
      const item: Record = {
        id: "2ee6930b-e09f-46d8-8a4b-000000000021",
        reference: data.reference.toUpperCase(), name: data.name,
        sku: data.sku.toUpperCase(), external_variant_id: data.external_variant_id,
        unit_cost_cents: data.unit_cost_cents,
        selling_price_cents: data.selling_price_cents,
        provenance: data.provenance || "",
        verified_at: data.verify_cost ? "2026-11-11T11:00:00Z" : null,
        verified_by_name: data.verify_cost ? "cost-merchant" : null,
        version: 1,
        review_status: "needs_review",
        created_at: "2026-11-11T11:00:00Z",
        updated_at: "2026-11-11T11:00:00Z"
      };
      item.review_status = status(item);
      items.push(item);
      response = item;
      responseStatus = 201;
    } else if (req.method() === "PATCH") {
      tracking.writes++;
      expect(req.headers()["x-csrftoken"]).toBe("csrf-costs-test");
      const data = req.postDataJSON();
      const item = items[0];
      expect(data.expected_version).toBe(item.version);
      Object.assign(item, {
        ...data,
        verified_at: data.verify_cost ? "2026-11-11T12:00:00Z" : item.verified_at,
        verified_by_name: data.verify_cost ? "cost-merchant" : item.verified_by_name,
        version: item.version + 1
      });
      item.review_status = status(item);
      response = item;
    } else if (req.method() === "GET" && url.pathname.endsWith("/history/")) {
      const item = items[0];
      response = {
        item_id: item.id,
        history: [{
          action: "update", version: item.version, by: "cost-merchant",
          created_at: "2026-11-11T12:00:00Z", before: {unit_cost_cents:700},
          after: {unit_cost_cents:item.unit_cost_cents, version:item.version}
        }]
      };
    } else {
      responseStatus = 404;
      response = { detail: "Não encontrado." };
    }
    await route.fulfill({ status: responseStatus, contentType: "application/json", body: JSON.stringify(response) });
  });
}

for (const width of [390, 768, 1440]) {
  test("Catálogo financeiro: cadastro, conferência e simulação em "+width+"px", async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width===390 ? 844 : 900 });
    await mockSession(page);
    const items: Record[] = [];
    const tracking = { writes: 0 };
    await mockCosts(page, items, tracking);

    await navigateCosts(page, width);
    await expect(page.getByText("Seu catálogo começa aqui")).toBeVisible();
    expect((await page.evaluate(()=>document.documentElement.scrollWidth))).toBeLessThanOrEqual(width+1);
    await page.getByRole("button", { name: "Cadastrar primeiro item" }).click();
    await page.getByRole("textbox", { name: /Nome do produto/ }).fill("Argola transparente 100 mm");
    await page.getByRole("textbox", { name: /Referência interna/ }).fill("ARG-100-T");
    await page.getByRole("textbox", { name: /SKU \(opcional\)/ }).fill("SKU-ARG100");
    await page.getByRole("textbox", { name: /Custo unitário manual/ }).fill("7,00");
    await page.getByRole("textbox", { name: /Preço de venda manual/ }).fill("29,90");
    await page.getByRole("dialog").getByRole("button", { name: "Cadastrar item", exact: true }).click();
    await expect(page.getByText("Item salvo com sucesso.")).toBeVisible();
    await expect(page.getByText("Argola transparente 100 mm")).toBeVisible();
    await expect(page.locator(".cost-table tbody tr").getByText("A conferir", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Editar Argola transparente 100 mm" }).click();
    await page.getByRole("textbox", { name: "Origem da conferência" }).fill("Conferido em nota de compra piloto");
    await page.getByRole("checkbox", { name: /Conferi o custo informado/ }).check();
    await page.getByRole("button", { name: "Salvar alterações" }).click();
    await expect(page.getByText("Conferido", { exact: true })).toBeVisible();
    expect(tracking.writes).toBe(2);

    await page.evaluate(() => window.scrollTo(0,0));
    await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(0);
    await page.screenshot({path:testInfo.outputPath("cost-catalog-"+width+".png"),fullPage:true});

    await page.getByRole("button", { name: "Simular" }).click();
    await expect(page.getByRole("heading", { name: "Simulador de rentabilidade" })).toBeVisible();
    await expect(page.getByText("Argola transparente 100 mm — referência ARG-100-T")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Custo da mercadoria" })).toHaveValue("7.00");
    await expect(page.getByRole("textbox", { name: "Subtotal dos produtos" })).toHaveValue("29.90");
    await expect(page.getByRole("textbox", { name: "Taxas do pagamento" })).toHaveValue("0");
    expect((await page.evaluate(()=>document.documentElement.scrollWidth))).toBeLessThanOrEqual(width+1);
  });
}

test("Analista vê custo, mas não consegue editar ou cadastrar", async ({ page }) => {
  await mockSession(page,"analyst");
  const items: Record[] = [{
    id:"2ee6930b-e09f-46d8-8a4b-000000000021",name:"Linha para teste",reference:"REF-100",
    sku:"LINHA-100",external_variant_id:"",unit_cost_cents:null,selling_price_cents:1500,
    provenance:"",verified_at:null,verified_by_name:null,version:1,review_status:"missing_cost",
    created_at:"2026-11-11T11:00:00Z",updated_at:"2026-11-11T11:00:00Z"
  }];
  const tracking={writes:0};
  await mockCosts(page,items,tracking);
  await navigateCosts(page,1440);
  await expect(page.getByText("Linha para teste")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cadastrar item" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Novo item" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Editar Linha para teste" })).toHaveCount(0);
  expect(tracking.writes).toBe(0);
});
