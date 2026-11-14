import {expect,test,type Page} from "@playwright/test";

// Auditoria de layout isolada: nenhum dado, credencial ou pagamento real.
const tenant={
  id:"d9b5f0bf-9cb8-4dd9-9926-9b16e0e623d7",
  name:"Loja de ensaio",slug:"loja-auditoria",
  status:"active",role:"owner",
};

async function setup(page:Page){
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      authenticated:true,
      user:{username:"visual-qa",display_name:"Lojista da auditoria"},
      tenants:[tenant],
    }),
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"no_enrollment_channel",
      summary:{total:0,active:0,paused:0},total_filtered:0,
      limit:20,offset:0,items:[],note:"Sem dados reais",
    }),
  }));
  await page.route("**/api/v1/tenants/**/campaign-drafts/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      items:[],total:0,limit:20,offset:0,
    }),
  }));
  await page.route("**/api/v1/tenants/**/nuvemshop/status/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      configured:false,connected:false,store_id:null,
      mode:"read_products_only",ready_for_write:false,
    }),
  }));
  await page.route("**/api/v1/tenants/**/settings/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      tenant_id:tenant.id,tenant_name:tenant.name,tenant_slug:tenant.slug,
      tenant_status:tenant.status,can_edit:true,version:1,
      public_link:null,
      branding:{
        program_name:"Clube Loja de Ensaio",
        primary_color:"#087F79",accent_color:"#37D5BB",
        support_email:"contato@example.invalid",
      },
      features:{
        public_signup_enabled:false,email_delivery_enabled:false,
        customer_preview_enabled:false,cashback_activation_enabled:false,
        custom_domain_available:false,
      },
    }),
  }));
  await page.route("**/api/v1/tenants/**/privacy/requests/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      pending_total:2,access_requests:1,deletion_requests:1,
      items:[
        {
          id:"9516bfb7-ce0f-4f40-8c60-b54b153e2e27",
          type:"deletion",received_at:"2026-11-11T10:00:00Z",
          status:"em_analise",protection_applied:true,
          report_available:false,downloaded:false,can_confirm:false,
        },
        {
          id:"e8662cbc-2774-49a9-8de8-bcf2cd5ef897",
          type:"data_access",received_at:"2026-11-11T11:00:00Z",
          status:"em_analise",protection_applied:false,
          report_available:true,downloaded:false,can_confirm:false,
        },
      ],
      note:"Pedidos recebidos",
    }),
  }));
}

async function assertNoHorizontalOverflow(page:Page,screen:string){
  const info=await page.evaluate(()=>{
    const screenWidth=window.innerWidth;
    const root=document.documentElement;
    return {
      horizontalOverflow:root.scrollWidth-screenWidth,
      viewportWidth:screenWidth,
      bodyOverflow:document.body.scrollWidth-screenWidth,
    };
  });
  expect(info.horizontalOverflow,screen+" / html").toBeLessThanOrEqual(1);
  expect(info.bodyOverflow,screen+" / body").toBeLessThanOrEqual(1);
}

for(const width of [320,360,390,430,768,1024,1440]){
  test("Painel e configurações sem corte nem zoom em "+width+"px",async({page},testInfo)=>{
    await page.setViewportSize({width,height:width<=390?700:900});
    await setup(page);
    await page.goto("/");
    await expect(page.getByRole("heading",{name:"Seu clube, sem complicação."})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Sua jornada, sem atalhos."})).toBeVisible();
    await expect(page.getByText("Pontos e resgates nas compras")).toBeVisible();
    await expect(page.getByText("Ainda não liberado")).toBeVisible();
    await assertNoHorizontalOverflow(page,"visão geral "+width);
    if(width<=1020){
      const opener=page.getByRole("button",{name:"Abrir menu"});
      await expect(opener).toBeVisible();
      await expect(opener).toHaveAttribute("aria-expanded","false");
      await expect(page.locator("#portal-sidebar")).toHaveAttribute("inert","");
      await opener.click();
      await expect(opener).toHaveAttribute("aria-expanded","true");
      await expect(page.locator("#portal-sidebar")).not.toHaveAttribute("inert","");
      await expect(page.getByRole("button",{name:"Fechar menu"})).toBeFocused();
      await expect.poll(()=>page.evaluate(()=>document.body.style.overflow))
        .toBe("hidden");
      await page.keyboard.press("Escape");
      await expect(opener).toHaveAttribute("aria-expanded","false");
      await expect(opener).toBeFocused();
      await expect(page.locator("#portal-sidebar")).toHaveAttribute("inert","");
      await expect.poll(()=>page.evaluate(()=>document.body.style.overflow))
        .toBe("");
      await opener.click();
    }
    await page.getByRole("button",{name:"Configurações"}).click();
    await expect(page.getByRole("heading",{name:"Aparência do programa"})).toBeVisible();
    await expect(page.getByRole("heading",{name:"Privacidade dos participantes"})).toBeVisible();
    await expect(page.getByText("Dados de contato protegidos.",{exact:false})).toBeVisible();
    await assertNoHorizontalOverflow(page,"configurações "+width);
    const emailInput=page.getByPlaceholder("atendimento@sualoja.com.br");
    await expect(emailInput).toBeVisible();
    if(width<=520){
      const fontSize=await emailInput.evaluate(el=>parseFloat(getComputedStyle(el).fontSize));
      expect(fontSize,"Safari não deve ampliar a página ao focar o campo")
        .toBeGreaterThanOrEqual(16);
    }
    const save=page.getByRole("button",{name:"Salvar alterações"});
    await expect(save).toBeDisabled();
    const preview=page.locator(".ss-preview-stage");
    await expect(preview).toBeVisible();
    await page.screenshot({
      path:testInfo.outputPath("merchant-settings-"+width+".png"),
      fullPage:true,
    });
  });
}

test("Cores personalizadas mantêm contraste em fundo claro e escuro",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await setup(page);
  await page.goto("/");
  await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.getByRole("button",{name:"Configurações"}).click();
  await expect(page.getByRole("heading",{name:"Aparência do programa"})).toBeVisible();
  const colors=page.locator(".ss-color-control input[type=color]");
  await expect(colors).toHaveCount(2);
  await colors.nth(0).fill("#ffffff");
  await expect.poll(()=>page.locator(".ss-preview-stage").evaluate(
    element=>getComputedStyle(element).color
  )).toBe("rgb(0, 0, 0)");
  await colors.nth(0).fill("#000000");
  await expect.poll(()=>page.locator(".ss-preview-stage").evaluate(
    element=>getComputedStyle(element).color
  )).toBe("rgb(255, 255, 255)");
  await colors.nth(1).fill("#111111");
  await expect.poll(()=>page.locator(".ss-preview-icon").evaluate(
    element=>getComputedStyle(element).color
  )).toBe("rgb(255, 255, 255)");
  await colors.nth(1).fill("#ffffff");
  await expect.poll(()=>page.locator(".ss-preview-icon").evaluate(
    element=>getComputedStyle(element).color
  )).toBe("rgb(0, 0, 0)");
  await assertNoHorizontalOverflow(page,"prévia com cores personalizadas");
});


// Auditoria transversal dos fluxos acessíveis, sem expor dados reais,
// com múltiplas larguras e funções opcionais desativadas.
for(const width of [320,390,768,1440]){
  test("Navegação integrada sem telas duplicadas ou corte em "+width+"px",async ({page},info)=>{
    await page.setViewportSize({width,height:900});
    await setup(page);
    await page.route("**/api/v1/tenants/**/sales/manual/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"manual_review_only",points_credited:false,items:[],
      }),
    }));
    await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"draft_only",activation_available:false,rule:null,
      }),
    }));
    await page.route("**/api/v1/tenants/**/program-terms/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"approval_required",public_signup_enabled:false,terms:null,
      }),
    }));
    await page.route("**/api/v1/tenants/**/enrollment-submissions/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"consents_pending_identity_verification",total:0,items:[],note:"Nenhuma adesão",
      }),
    }));
    await page.route("**/api/v1/tenants/**/campaign-drafts/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        items:[],total:0,limit:20,offset:0,
      }),
    }));
    await page.goto("/");
    const screens=[
      ["Programa","Seu programa de fidelidade."],
      ["Clientes","Participantes do clube."],
      ["Vendas","Pedidos e vendas."],
      ["Campanhas","Uma campanha em poucos passos."],
      ["Resultados","Resultados que importam."],
      ["Custo dos benefícios","Quanto custa meu programa?"],
      ["Custos por SKU","Conheça o custo antes do benefício."],
      ["Conciliação","Valide variantes antes de importar."],
      ["Configurações","Sua loja, do seu jeito."],
    ] as const;
    for(const [nav,title] of screens){
      if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
      await page.locator("#portal-sidebar").getByRole("button",{name:new RegExp("^"+nav+"(?:\\s|$)")}).click();
      await expect(page.getByRole("heading",{level:1,name:title})).toBeVisible();
      if(nav==="Configurações"){
        await expect(page.getByRole("heading",{name:"Regras do clube"})).toHaveCount(0);
        await expect(page.getByRole("link",{name:"Abrir página do cliente"}))
          .toHaveAttribute("href","/clube/loja-auditoria");
      }
      if(nav==="Vendas"){
        await expect(page.getByRole("heading",{name:"Informações da compra"})).toBeVisible();
        await expect(page.getByLabel("Qual foi o valor?")).toBeVisible();
      }
      if(nav==="Resultados"){
        await expect(page.getByRole("heading",{name:"Seu clube em números que fazem sentido."}))
          .toBeVisible();
        await expect(page.getByText("Ainda não medido")).toBeVisible();
      }
      await assertNoHorizontalOverflow(page,nav+" "+width);
      if(width===390&&["Vendas","Resultados","Programa"].includes(nav)){
        await page.screenshot({path:info.outputPath(
          "audit-"+nav.toLowerCase()+"-"+width+".png"),fullPage:true});
      }
    }
  });
}
