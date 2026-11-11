import { expect, test, type Page } from "@playwright/test";

const store = {
  id: "ad56ba78-42e9-4111-935f-87c761b3a123",
  name: "Bibelô — ambiente piloto",
  slug: "bibelo-piloto",
  status: "draft",
  role: "owner"
};

async function mockAuthenticated(page: Page) {
  await page.context().addCookies([
    { name: "csrftoken", value: "csrf-for-ui-test", domain: "127.0.0.1", path: "/" }
  ]);
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      authenticated: true,
      user: { username: "lojista-piloto", display_name: "Loja piloto" },
      tenants: [store]
    })
  }));
}

async function enterMargin(page: Page, width: number) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
  if (width <= 1020) await page.getByRole("button", { name: "Abrir menu" }).click();
  await page.getByRole("button", { name: "Rentabilidade" }).click();
  if (width <= 1020) {
    await expect.poll(async () => page.locator(".portal-side").evaluate(
      node => node.getBoundingClientRect().right
    )).toBeLessThan(2);
  }
  await expect(page.getByRole("heading", { name: "Simulador de rentabilidade" })).toBeVisible();
}

for (const width of [390, 768, 1440]) {
  test("portal real é responsivo e calcula na API: " + width, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await mockAuthenticated(page);
    let called = false;
    await page.route("**/api/v1/tenants/**/margin-simulations/", async route => {
      called = true;
      const payload = route.request().postDataJSON();
      expect(payload.eligible_subtotal_cents).toBe(20000);
      expect(payload.existing_discounts_cents).toBe(1000);
      expect(payload.cost_of_goods_cents).toBe(11000);
      expect(route.request().headers()["x-csrftoken"]).toBe("csrf-for-ui-test");
      expect(route.request().url()).toContain(store.id);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "within_target",
          eligible_net_revenue_cents: 19000,
          estimated_cashback_exposure_cents: 380,
          contribution_before_cents: 5800,
          contribution_after_cents: 5420,
          margin_after_bps: 2852,
          safe_cashback_budget_cents: 2950,
          maximum_safe_cashback_bps: 1552,
          minimum_margin_bps: 1500,
          automatically_approved: false
        })
      });
    });

    await enterMargin(page, width);
    await expect(page.getByText("Pronto para calcular")).toBeVisible();
    await expect(page.getByRole("button", { name: "Calcular no servidor" })).toBeVisible();

    const scroll = await page.evaluate(() =>
      ({ doc: document.documentElement.scrollWidth, viewport: window.innerWidth })
    );
    expect(scroll.doc, "overflow horizontal: " + JSON.stringify(scroll)).toBeLessThanOrEqual(scroll.viewport + 1);

    await page.getByRole("button", { name: "Calcular no servidor" }).click();
    await expect(page.getByText("Dentro da meta simulada")).toBeVisible();
    expect(called).toBe(true);
    // O botão fica abaixo da primeira dobra; capture após voltar ao topo
    // para evitar posicionamento deslocado do menu fixo no screenshot fullPage.
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.screenshot({
      path: testInfo.outputPath("portal-margin-" + width + ".png"), fullPage: true
    });

    await page.getByRole("button", { name: "Custo ausente" }).click();
    await expect(page.getByText("Pronto para calcular")).toBeVisible();
    await expect(page.getByText("Dentro da meta simulada")).toHaveCount(0);
  });
}

test("a tela de login não expõe números demonstrativos", async ({ page }) => {
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ authenticated: false, user: null, tenants: [] })
  }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bem-vindo de volta." })).toBeVisible();
  await expect(page.getByLabel("Usuário")).toBeVisible();
  await expect(page.getByLabel("Senha")).toHaveAttribute("type", "password");
  await expect(page.getByText("Créditos emitidos")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Conhecer demonstração visual" })).toHaveAttribute("href", "/demo");
});

test("login e logout respeitam sessão e CSRF de frontend", async ({ page }) => {
  await page.context().addCookies([
    { name: "csrftoken", value: "csrf-e2e", domain: "127.0.0.1", path: "/" }
  ]);
  let authenticated = false;
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify(authenticated ? {
      authenticated: true, user: { username: "pilot", display_name: "Lojista" }, tenants: [store]
    } : { authenticated: false, user: null, tenants: [] })
  }));
  await page.route("**/api/v1/auth/login/", async route => {
    expect(route.request().headers()["x-csrftoken"]).toBe("csrf-e2e");
    expect(route.request().postDataJSON()).toEqual({
      username: "pilot", password: "example-only"
    });
    authenticated = true;
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ authenticated: true, tenants: [store] })
    });
  });
  await page.route("**/api/v1/auth/logout/", async route => {
    expect(route.request().headers()["x-csrftoken"]).toBe("csrf-e2e");
    authenticated = false;
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ authenticated: false })
    });
  });

  await page.goto("/");
  await page.getByLabel("Usuário").fill("pilot");
  await page.getByLabel("Senha").fill("example-only");
  await page.getByRole("button", { name: "Acessar minha loja" }).click();
  await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
  await expect(page.getByText("Bibelô — ambiente piloto").first()).toBeVisible();
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("heading", { name: "Bem-vindo de volta." })).toBeVisible();
});
