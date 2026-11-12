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
  await expect(page.getByLabel("E-mail")).toBeVisible();
  await expect(page.getByLabel("Senha",{exact:true})).toHaveAttribute("type", "password");
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
      email: "pilot@example.invalid", password: "example-only"
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
  await page.getByLabel("E-mail").fill("pilot@example.invalid");
  await page.getByLabel("Senha",{exact:true}).fill("example-only");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "O próximo passo da sua loja." })).toBeVisible();
  await expect(page.getByText("Bibelô — ambiente piloto").first()).toBeVisible();
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("heading", { name: "Bem-vindo de volta." })).toBeVisible();
});


test("registro do lojista sem Nuvemshop exige confirmação e senha forte",async ({page})=>{
  await page.context().addCookies([
    {name:"csrftoken",value:"csrf-merchant-test",domain:"127.0.0.1",path:"/"}
  ]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      authenticated:false,user:null,tenants:[]
    })
  }));
  let submissions=0;
  await page.route("**/api/v1/auth/register/",route=>{
    submissions++;
    expect(route.request().headers()["x-csrftoken"]).toBe("csrf-merchant-test");
    const data=route.request().postDataJSON();
    expect(data.email).toBe("lojista@example.invalid");
    expect(data.store_name).toBe("Armarinho");
    return route.fulfill({status:202,contentType:"application/json",
      body:JSON.stringify({detail:"Verifique o e-mail."})});
  });
  await page.setViewportSize({width:390,height:844});
  await page.goto("/");
  await page.getByRole("button",{name:"Criar conta grátis"}).click();
  await expect(page).toHaveURL(/\/cadastrar$/);
  await expect(page.getByRole("heading",{name:"Crie sua conta."})).toBeVisible();
  await page.getByLabel("Seu nome").fill("Lojista");
  await page.getByLabel("Nome da loja").fill("Armarinho");
  await page.getByLabel("E-mail").fill("lojista@example.invalid");
  await page.getByLabel("Senha",{exact:true}).fill("SenhaTeste-2026-forte!");
  await page.getByLabel("Confirmar senha").fill("SenhaDiferente-2026!");
  await page.getByRole("button",{name:"Criar minha conta"}).click();
  await expect(page.getByRole("alert")).toContainText("não conferem");
  expect(submissions).toBe(0);
  await page.getByLabel("Confirmar senha").fill("SenhaTeste-2026-forte!");
  await page.getByRole("button",{name:"Criar minha conta"}).click();
  await expect(page.getByRole("heading",{name:"Verifique seu e-mail."})).toBeVisible();
  await expect(page.getByText("Se existir um cadastro aguardando confirmação",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:"Já tenho conta: recuperar acesso"})).toBeVisible();
  expect(submissions).toBe(1);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("recuperação envia instrução genérica sem revelar se e-mail existe",async ({page})=>{
  await page.context().addCookies([
    {name:"csrftoken",value:"csrf-reset",domain:"127.0.0.1",path:"/"}
  ]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({authenticated:false,user:null,tenants:[]})
  }));
  await page.route("**/api/v1/auth/password-reset/request/",route=>{
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({email:"nobody@example.invalid"});
    return route.fulfill({status:202,contentType:"application/json",
      body:JSON.stringify({detail:"Se existir, enviaremos instruções."})});
  });
  await page.goto("/");
  await page.getByRole("button",{name:"Esqueci minha senha"}).click();
  await page.getByLabel("E-mail").fill("nobody@example.invalid");
  await page.getByRole("button",{name:"Enviar link de recuperação"}).click();
  await expect(page.getByRole("heading",{name:"Confira seu e-mail."})).toBeVisible();
  await expect(page.locator(".portal-login-card")).not.toContainText("não existe");
});

test("confirmação de e-mail apaga token da URL e entra na loja",async ({page})=>{
  await page.context().addCookies([
    {name:"csrftoken",value:"csrf-confirm",domain:"127.0.0.1",path:"/"}
  ]);
  let confirmed=false;
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify(confirmed?{
      authenticated:true,user:{username:"internal",display_name:"Lojista"},
      tenants:[{...store,name:"Loja criada pelo lojista"}]
    }:{authenticated:false,user:null,tenants:[]})
  }));
  await page.route("**/api/v1/auth/register/confirm/",route=>{
    expect(route.request().postDataJSON()).toEqual({token:"synthetic-token-only"});
    confirmed=true;
    return route.fulfill({contentType:"application/json",
      body:JSON.stringify({authenticated:true,detail:"Conta confirmada."})});
  });
  await page.goto("/confirmar-conta#token=synthetic-token-only");
  await expect(page).toHaveURL(/\/confirmar-conta$/);
  await page.getByRole("button",{name:"Confirmar e acessar"}).click();
  await expect(page.getByText("Loja criada pelo lojista").first()).toBeVisible();
});

test("rota de redefinição não vaza token na URL nem ao confirmar",async ({page})=>{
  await page.context().addCookies([{name:"csrftoken",value:"csrf-new",domain:"127.0.0.1",path:"/"}]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({authenticated:false,user:null,tenants:[]})
  }));
  await page.route("**/api/v1/auth/password-reset/confirm/",route=>{
    expect(route.request().postDataJSON()).toEqual({
      token:"reset-synthetic",password:"NovaSenhaSegura-2026!"
    });
    return route.fulfill({contentType:"application/json",body:JSON.stringify({detail:"Senha atualizada."})});
  });
  await page.goto("/redefinir-senha#token=reset-synthetic");
  await expect(page).toHaveURL(/\/redefinir-senha$/);
  await page.getByLabel("Nova senha").fill("NovaSenhaSegura-2026!");
  await page.getByLabel("Confirmar senha").fill("NovaSenhaSegura-2026!");
  await page.getByRole("button",{name:"Salvar nova senha"}).click();
  await expect(page.getByText("Senha redefinida.")).toBeVisible();
  await expect(page).toHaveURL("/");
});
