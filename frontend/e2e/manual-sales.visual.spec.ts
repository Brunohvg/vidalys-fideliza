import {expect,test,type Page} from "@playwright/test";

const tenant={
  id:"a904014f-83df-4a04-a20a-b24062fb6433",
  name:"Loja Balcão",slug:"loja-balcao",status:"active",role:"owner",
};
const member={
  id:"bff72f53-1234-481a-8524-ef6fc310ff10",
  customer_reference:null,display_name:"Cliente Confirmado",
  contact_email:"cliente@example.invalid",status:"active",
  consented_at:"2026-11-12T12:00:00Z",joined_at:"2026-11-12T12:00:00Z",
  last_program_activity_at:null,consent_channel:"customer_portal",
  points_balance:null,cashback_balance_cents:null,cashback_pending_cents:null,
  cashback_reserved_cents:null,balance_status:"not_implemented",
};

async function mock(page:Page) {
  await page.context().addCookies([{
    name:"csrftoken",value:"sales-csrf-synthetic-qa",url:"http://127.0.0.1:4173",
  }]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      authenticated:true,user:{username:"sales-qa",display_name:"QA Lojista"},
      tenants:[tenant],
    }),
  }));
  await page.route("**/api/v1/tenants/**/participants/**",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      source:"verified_opt_in_only",data_status:"consent_verified",
      summary:{total:1,active:1,paused:0},total_filtered:1,limit:20,
      offset:0,items:[member],note:"Sem saldo ativo",
    }),
  }));
  await page.route("**/api/v1/tenants/**/sales/manual/",route=>{
    if(route.request().method()==="GET")return route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"manual_review_only",points_credited:false,items:[],
      }),
    });
    return route.fulfill({
      status:201,contentType:"application/json",body:JSON.stringify({
        already_recorded:false,sale:{
          id:"0cb247c3-0cc5-499b-834a-8870c9328d41",channel:"counter",
          reference:"VENDA-0042",participant_id:member.id,
          participant_name:"Cliente Confirmado",eligible_amount_cents:10000,
          reported_paid_at:"2026-11-13T16:00:00Z",
          evidence_reference:"CUPOM-0042",state:"awaiting_review",
          submitted_by_me:true,created_at:"2026-11-13T16:00:00Z",reviewed_at:null,
          points_credited:false,cashback_credited:false,
        },
      }),
    });
  });
  await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",route=>{
    if(route.request().method()==="GET")return route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"draft_only",activation_available:false,rule:null,
      }),
    });
    return route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        mode:"draft_only",activation_available:false,version:1,points:1,
        per_cents:100,hold_days:7,validity_days:180,
        example_for_100_reais:100,points_credited:false,
      }),
    });
  });
}

for(const width of [390,1440]){
  test("Registrar venda manual não credita pontos e funciona em "+width+"px",async ({page})=>{
    await page.setViewportSize({width,height:850});
    await mock(page);
    let saved=0;
    await page.route("**/api/v1/tenants/**/sales/manual/",async route=>{
      if(route.request().method()!=="POST")return route.fallback();
      saved+=1;
      const payload=route.request().postDataJSON();
      expect(payload.reference).toBe("CUPOM-0042");
      expect(payload.eligible_amount_cents).toBe(10000);
      expect(payload.participant_id).toBe(member.id);
      expect(payload.evidence_reference).toBe("CUPOM-0042");
      expect(route.request().headers()["x-csrftoken"]).toBe("sales-csrf-synthetic-qa");
      await route.fulfill({status:201,contentType:"application/json",body:JSON.stringify({
        already_recorded:false,sale:{
          id:"0cb247c3-0cc5-499b-834a-8870c9328d41",channel:"counter",
          reference:"VENDA-0042",participant_id:member.id,
          participant_name:"Cliente Confirmado",eligible_amount_cents:10000,
          reported_paid_at:payload.reported_paid_at,evidence_reference:"CUPOM-0042",
          state:"awaiting_review",submitted_by_me:true,created_at:"2026-11-13T16:00:00Z",
          reviewed_at:null,points_credited:false,cashback_credited:false,
        },
      })});
    });
    await page.goto("/");
    if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
    await page.locator(".portal-nav").getByRole("button",{name:"Vendas"}).click();
    await expect(page.getByRole("heading",{name:"Informações da compra"})).toBeVisible();
    await expect(page.getByRole("button",{name:"Venda no balcão"})).toBeVisible();
    await expect(page.getByRole("button",{name:"A compra foi em outra data?"})).toHaveAttribute("aria-expanded","false");
    await page.getByLabel("Qual foi o valor?").fill("100,00");
    await page.getByLabel("Número do cupom ou recibo").fill("0042");
    await page.locator("#vf-sale-client").selectOption(member.id);
    await page.getByRole("button",{name:"Registrar venda",exact:true}).click();
    await expect(page.getByText("Venda registrada. Confira o comprovante abaixo.",{
      exact:false,
    })).toBeVisible();
    expect(saved).toBe(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
      .toBeLessThanOrEqual(1);
  });
}

test("Regra configurável é apenas rascunho e pertence ao Programa",async ({page})=>{
  await mock(page);
  let submitted=0;
  await page.route("**/api/v1/tenants/**/loyalty/point-rule-draft/",async route=>{
    if(route.request().method()!=="POST")return route.fallback();
    submitted+=1;
    expect(route.request().postDataJSON()).toEqual({
      points:1,per_cents:100,hold_days:7,validity_days:180,
    });
    await route.fulfill({contentType:"application/json",body:JSON.stringify({
      mode:"draft_only",activation_available:false,version:1,
      points:1,per_cents:100,hold_days:7,validity_days:180,
      example_for_100_reais:100,points_credited:false,
    })});
  });
  await page.goto("/");
  await page.locator(".portal-nav").getByRole("button",{name:"Programa"}).click();
  await page.getByRole("group",{name:"Editar benefícios"}).getByRole("button",{name:"Regra de pontos"}).click();
  await expect(page.getByRole("heading",{name:"Como o participante vai ganhar pontos?"})).toBeVisible();
  await expect(page.getByText("Não publicado")).toBeVisible();
  await page.getByRole("button",{name:"Salvar rascunho"}).click();
  await expect(page.getByText("Regra salva como rascunho.",{exact:false})).toBeVisible();
  expect(submitted).toBe(1);
});

test("Segundo administrador confere venda sem gerar pontos",async ({page})=>{
  await mock(page);
  await page.route("**/api/v1/tenants/**/sales/manual/",route=>route.fulfill({
    contentType:"application/json",body:JSON.stringify({
      mode:"manual_review_only",points_credited:false,items:[{
        id:"0cb247c3-0cc5-499b-834a-8870c9328d41",channel:"counter",
        reference:"VENDA-0042",participant_id:member.id,
        participant_name:"Cliente Confirmado",eligible_amount_cents:10000,
        reported_paid_at:"2026-11-13T16:00:00Z",
        evidence_reference:"CUPOM-0042",state:"awaiting_review",
        submitted_by_me:false,created_at:"2026-11-13T16:00:00Z",
        reviewed_at:null,points_credited:false,cashback_credited:false,
      }],
    }),
  }));
  let reviewed=0;
  await page.route("**/api/v1/tenants/**/sales/manual/**/review/",async route=>{
    reviewed+=1;
    expect(route.request().postDataJSON()).toEqual({
      decision:"approve",note:"Cupom e pagamento conferidos no caixa.",
    });
    await route.fulfill({contentType:"application/json",body:JSON.stringify({
      sale:{id:"0cb247c3-0cc5-499b-834a-8870c9328d41",
        state:"verified_manual",points_credited:false},
      manual_evidence_reviewed:true,independent_payment_proof:false,
      points_credited:false,
    })});
  });
  await page.goto("/");
  await page.locator(".portal-nav").getByRole("button",{name:"Vendas"}).click();
  await page.getByRole("button",{name:/Conferir vendas/}).click();
  await expect(page.getByText("Aguardando conferência")).toBeVisible();
  await page.getByRole("button",{name:"Conferir venda"}).click();
  await expect(page.getByText("CUPOM-0042",{exact:false})).toBeVisible();
  await page.getByPlaceholder("Ex.: Cupom e pagamento conferidos no caixa.")
    .fill("Cupom e pagamento conferidos no caixa.");
  await page.getByRole("button",{name:"Confirmar conferência"}).click();
  await expect(page.getByText("Conferência registrada. Nenhum ponto foi creditado."))
    .toBeVisible();
  expect(reviewed).toBe(1);
});

test("Não participante exige escolha explícita e data antiga fica oculta",async ({page})=>{
  await mock(page);
  let captured:{participant_id:string|null;reference:string}|null=null;
  await page.route("**/api/v1/tenants/**/sales/manual/",async route=>{
    if(route.request().method()!=="POST")return route.fallback();
    captured=route.request().postDataJSON();
    return route.fulfill({status:201,contentType:"application/json",body:JSON.stringify({
      already_recorded:false,sale:{state:"awaiting_member"},
    })});
  });
  await page.goto("/");
  await page.locator(".portal-nav").getByRole("button",{name:"Vendas"}).click();
  await page.getByLabel("Qual foi o valor?").fill("59,90");
  await page.getByLabel("Número do cupom ou recibo").fill("0071");
  await page.getByRole("button",{name:"Registrar venda",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Selecione um participante");
  expect(captured).toBeNull();
  await page.locator("#vf-sale-client").selectOption("");
  await expect(page.getByText("Esta venda ficará registrada sem pontos.",{exact:false}))
    .toBeVisible();
  await page.getByRole("button",{name:"Registrar venda",exact:true}).click();
  await expect(page.getByText("Venda registrada sem participante.",{exact:false}))
    .toBeVisible();
  expect(captured).toMatchObject({participant_id:null,reference:"CUPOM-0071"});
});
