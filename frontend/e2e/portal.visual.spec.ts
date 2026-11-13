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
  await page.getByRole("button", { name: "Custo dos benefícios" }).click();
  if (width <= 1020) {
    await expect.poll(async () => page.locator(".portal-side").evaluate(
      node => node.getBoundingClientRect().right
    )).toBeLessThan(2);
  }
  await expect(page.getByRole("heading", { name: "Quanto pode custar uma recompensa?" })).toBeVisible();
}

for (const width of [390, 768, 1440]) {
 test("portal simula custo dos pontos sem pedir acesso financeiro em "+width+"px",
 async({page},testInfo)=>{
  await page.setViewportSize({width,height:width===390?844:900});
  await mockAuthenticated(page);
  let attempts=0;
  await page.route("**/api/v1/tenants/**/margin-simulations/",route=>{
   attempts+=1;
   return route.fulfill({status:405,contentType:"application/json",
    body:JSON.stringify({detail:"Simulação não permitida."})});
  });
  await enterMargin(page,width);
  await expect(page.getByText("Isso não é o lucro da loja.",{exact:false})).toBeVisible();
  await page.getByRole("textbox",{name:"Valor da próxima compra"}).fill("200,00");
  await page.getByRole("textbox",{name:"Desconto por recompensa"}).fill("5,00");
  await page.getByRole("spinbutton",{name:"Quantidade máxima de resgates"}).fill("20");
  await expect(page.getByText("R$ 100,00",{exact:false})).toBeVisible();
  await expect(page.getByText("R$ 195,00",{exact:false})).toBeVisible();
  expect(attempts).toBe(0);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({path:testInfo.outputPath("simple-cost-"+width+".png"),fullPage:true});
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

test("conta técnica sem empresa exibe diagnóstico sem associar loja alheia", async ({ page }) => {
  await page.route("**/api/v1/auth/session/", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      authenticated: true, store_link_status: "missing",
      user: { username: "technical-admin", display_name: "Administrador QA" },
      tenants: [],
    }),
  }));
  await page.goto("/");
  await expect(page.getByRole("heading", {
    name: "Sua conta está ativa, mas sem empresa associada",
  })).toBeVisible();
  await expect(page.getByText("Contas técnicas criadas no Django Admin", {
    exact: false,
  })).toBeVisible();
  await expect(page.getByText("Bibelô — ambiente piloto")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Trocar de conta" })).toBeVisible();
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

test("link de nova conta vence o painel antigo sem mesclar sessões", async ({page}) => {
  await page.context().addCookies([
    {name:"csrftoken",value:"csrf-other-user",domain:"127.0.0.1",path:"/"},
  ]);
  let confirmed=false;
  let confirmCalls=0;
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify(confirmed?{
      authenticated:true,store_link_status:"linked",
      user:{username:"new-owner",display_name:"Novo Lojista"},
      tenants:[{...store,id:"22222222-2222-4222-8222-222222222222",
        name:"Nova empresa confirmada"}],
    }:{
      authenticated:true,store_link_status:"linked",
      user:{username:"old-owner",display_name:"Lojista Anterior"},
      tenants:[store],
    }),
  }));
  await page.route("**/api/v1/auth/register/confirm/",route=>{
    confirmCalls++;
    expect(route.request().postDataJSON()).toEqual({token:"token-confirm-another"});
    expect(route.request().headers()["x-csrftoken"]).toBe("csrf-other-user");
    confirmed=true;
    return route.fulfill({contentType:"application/json",body:JSON.stringify({
      authenticated:true,store_linked:true,store_id:"22222222-2222-4222-8222-222222222222",
      detail:"Conta e empresa confirmadas.",
    })});
  });
  await page.goto("/confirmar-conta#token=token-confirm-another");
  await expect(page.getByRole("heading",{name:"Confirme seu e-mail."})).toBeVisible();
  await expect(page.getByText("Lojista Anterior")).toBeVisible();
  await expect(page.getByText("Ao confirmar o e-mail",{exact:false})).toBeVisible();
  await expect(page).toHaveURL(/\/confirmar-conta$/);
  expect(confirmCalls).toBe(0);
  await page.getByRole("button",{name:"Confirmar e acessar"}).click();
  await expect(page.getByText("Nova empresa confirmada").first()).toBeVisible();
  await expect(page.getByText("Bibelô — ambiente piloto")).toHaveCount(0);
  await expect(page).toHaveURL("/");
  expect(confirmCalls).toBe(1);
});

test("trocar de formulário remove dados da conta anterior",async ({page})=>{
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:false,user:null,tenants:[]}),
  }));
  await page.goto("/");
  await page.getByRole("button",{name:"Criar conta grátis"}).click();
  await page.getByLabel("Seu nome").fill("Nome antigo");
  await page.getByLabel("Nome da loja").fill("Empresa antiga");
  await page.getByLabel("E-mail").fill("outro@example.invalid");
  await page.getByLabel("Senha",{exact:true}).fill("SenhaTemporaria-2026!");
  await page.getByRole("button",{name:"Voltar ao login"}).click();
  await expect(page.getByLabel("E-mail")).toHaveValue("");
  await expect(page.getByLabel("Senha",{exact:true})).toHaveValue("");
  await page.getByRole("button",{name:"Criar conta grátis"}).click();
  await expect(page.getByLabel("Seu nome")).toHaveValue("");
  await expect(page.getByLabel("Nome da loja")).toHaveValue("");
  await expect(page.getByLabel("E-mail")).toHaveValue("");
  await expect(page.getByLabel("Senha",{exact:true})).toHaveValue("");
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
  await expect(page).toHaveURL("/redefinir-senha");
  await page.getByRole("button",{name:"Voltar ao login"}).click();
  await expect(page).toHaveURL("/");
});
