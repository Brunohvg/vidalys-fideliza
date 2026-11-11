import { expect, test } from "@playwright/test";

const tenant = {
  id: "a5ee4147-b23c-4ad2-ae44-c3f5aaf13ed0",
  name: "Loja de teste",
  slug: "loja-teste",
  status: "draft",
  role: "owner"
};

for (const width of [390, 768, 1440]) {
  test("Planejador de campanhas com limite de orçamento em " + width + "px", async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.context().addCookies([
      { name: "csrftoken", value: "csrf-planner-mock", domain: "127.0.0.1", path: "/" }
    ]);
    await page.route("**/api/v1/auth/session/", route => route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        user: { username: "merchant-test", display_name: "Conta teste" },
        tenants: [tenant]
      })
    }));

    let requests = 0;
    await page.route("**/api/v1/tenants/**/campaign-plans/preview/", async route => {
      requests++;
      expect(route.request().method()).toBe("POST");
      expect(route.request().headers()["x-csrftoken"]).toBe("csrf-planner-mock");
      expect(route.request().url()).toContain(tenant.id);
      const input = route.request().postDataJSON();
      expect(input.projected_paid_orders).toBe(100);
      expect(input.eligible_subtotal_cents).toBe(20000);
      expect(input.existing_discounts_cents).toBe(1000);
      const unknown = input.cost_of_goods_cents === null;
      const safe = input.campaign_budget_cents === 60000;
      const status = unknown ? "cost_unknown" : safe ? "within_limits" : "campaign_budget_exceeded";
      await route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          mode: "planning_only", status,
          projected_paid_orders: 100, cashback_rate_bps: 200,
          per_order_net_revenue_cents: 19000, per_order_cashback_cents: 380,
          campaign_budget_cents: input.campaign_budget_cents,
          already_committed_cents: 2000,
          available_campaign_budget_cents: safe ? 58000 : 18000,
          projected_new_exposure_cents: 38000,
          projected_total_exposure_cents: 40000,
          estimated_order_capacity: safe ? 152 : 47,
          budget_within_limit: safe,
          margin_within_target: !unknown,
          maximum_margin_rate_bps: unknown ? null : 2184,
          maximum_budget_rate_bps: safe ? 306 : 94,
          suggested_limit_rate_bps: unknown ? null : safe ? 306 : 94,
          per_order_contribution_after_cents: unknown ? null : 6620,
          projected_contribution_after_cents: unknown ? null : 662000,
          automatically_approved: false,
          warnings: ["Os valores são hipotéticos."]
        })
      });
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
    if (width <= 1020) await page.getByRole("button", { name: "Abrir menu" }).click();
    await page.getByRole("button", { name: /^Campanhas/ }).click();
    if (width <= 1020) {
      await expect.poll(() => page.locator(".portal-side").evaluate(node => node.getBoundingClientRect().right)).toBeLessThan(2);
    }
    // O planejador original permanece disponível na área avançada.
    await page.getByRole("button", { name: /Abrir análise avançada/ }).click();
    await expect(page.getByRole("heading", { name: "Seu plano de fidelidade" })).toBeVisible();
    await expect(page.getByText("Os campos estão preenchidos com exemplos")).toBeVisible();

    let geometry = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(geometry.scroll, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.width + 1);

    await page.getByRole("button", { name: "Analisar orçamento e margem" }).click();
    await expect(page.getByText("O orçamento não comporta o volume")).toBeVisible();
    await expect(page.getByText("R$ 400,00")).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.screenshot({ path: testInfo.outputPath("campaign-risk-" + width + ".png"), fullPage: true });

    await page.getByRole("button", { name: "Ajustar orçamento" }).click();
    await expect(page.getByText("Pronto para simular")).toBeVisible();
    await page.getByRole("button", { name: "Analisar orçamento e margem" }).click();
    await expect(page.getByText("Dentro dos limites simulados")).toBeVisible();

    await page.getByRole("button", { name: "Sem custo validado" }).click();
    await page.getByRole("button", { name: "Analisar orçamento e margem" }).click();
    await expect(page.getByText("Custo não informado")).toBeVisible();
    await expect(page.getByText("Não calculável")).toBeVisible();
    await expect(page.getByText("Dentro dos limites simulados")).toHaveCount(0);
    expect(requests).toBe(3);

    geometry = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(geometry.scroll, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.width + 1);
  });
}
