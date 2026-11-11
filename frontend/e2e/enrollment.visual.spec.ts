import {test,expect,type Page} from "@playwright/test";

async function setup(page:Page){
  await page.context().addCookies([{
    name:"csrftoken",value:"test-enrollment-only",url:"http://127.0.0.1:4173"
  }]);
  await page.route("**/api/v1/auth/session/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({authenticated:false,user:null,tenants:[]})
  }));
  await page.route("**/api/v1/public/enrollment/preview/",route=>route.fulfill({
    contentType:"application/json",
    body:JSON.stringify({
      mode:"explicit_consent_only",store_name:"Loja Exemplo",
      terms:{id:"57a26bb4-39aa-4198-a7f2-95d6af5b0021",
        version:"v1",title:"Regulamento de adesão",
        body:"Este é um regulamento fictício utilizado somente no ambiente de testes. "
          +"Aceitar este convite não significa receber saldo ou crédito no programa e "
          +"o vínculo com o comprador precisará ser confirmado pela loja.",
        approved_at:"2026-11-11T12:00:00Z"},
      expires_at:"2026-11-12T12:00:00Z",
      identity_verified:false,benefits_active:false
    })
  }));
  await page.route("**/api/v1/public/enrollment/accept/",route=>route.fulfill({
    status:201,contentType:"application/json",
    body:JSON.stringify({
      status:"pending_verification",
      receipt_id:"b746ab22-fd49-43d6-9f7e-49df8fbb3a73",
      terms_version:"v1",participant_created:false,cashback_enabled:false,
      message:"Seu aceite foi registrado. A loja ainda precisa confirmar sua identidade."
    })
  }));
}

for(const width of [390,768,1440]){
  test("Aceite público com consentimentos independentes em "+width+"px", async ({page})=>{
    await page.setViewportSize({width,height:850});
    await setup(page);
    await page.goto("/participar#convite=token-qa-somente-front");
    await expect(page.getByRole("heading",{name:"Faça parte de uma relação que vale mais."})).toBeVisible();
    await expect(page.getByText("Regulamento de adesão")).toBeVisible();
    await expect(page.getByText("não significa receber saldo ou crédito",{exact:false})).toBeVisible();
    await page.getByRole("textbox",{name:"Seu nome"}).fill("Pessoa Interessada");
    await page.getByRole("textbox",{name:"Seu e-mail"}).fill("pessoa@example.invalid");
    await expect(page.getByRole("button",{name:"Registrar meu aceite"})).toBeDisabled();
    await page.getByRole("checkbox",{name:/Li e aceito os termos/}).check();
    await expect(page.getByRole("checkbox",{name:/comunicações promocionais/})).not.toBeChecked();
    await page.getByRole("button",{name:"Registrar meu aceite"}).click();
    await expect(page.getByRole("heading",{name:"Aceite registrado."})).toBeVisible();
    await expect(page.getByText("não gera saldo, desconto, pontos ou cashback",{exact:false})).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}


for(const width of [390,768,1440]){
  test("Página própria da loja solicita adesão com aviso de privacidade em "+width+"px",
    async ({page})=>{
      await page.setViewportSize({width,height:850});
      await page.context().addCookies([{
        name:"csrftoken",value:"test-public-store-only",url:"http://127.0.0.1:4173"
      }]);
      await page.route("**/api/v1/auth/session/",route=>route.fulfill({
        contentType:"application/json",
        body:JSON.stringify({authenticated:false,user:null,tenants:[]})
      }));
      await page.route("**/api/v1/public/programs/loja-jardim/",route=>route.fulfill({
        contentType:"application/json",
        body:JSON.stringify({
          mode:"public_pre_enrollment",store_name:"Loja Jardim",store_slug:"loja-jardim",
          terms:{id:"57a26bb4-39aa-4198-a7f2-95d6af5b0021",
            version:"v1",title:"Programa da Loja Jardim",
            body:"Ao participar, você entende que a solicitação passará por revisão e "
              +"nenhum cashback, ponto ou desconto será liberado automaticamente. "
              +"Este programa ainda está em homologação.",
            privacy_notice:"A Loja Jardim coletará nome e e-mail para confirmar sua identidade, "
              +"processar sua solicitação e gerenciar sua participação. "
              +"O titular pode solicitar acesso, correção ou eliminação pelos canais oficiais da loja.",
            approved_at:"2026-11-11T12:00:00Z"},
          identity_verification_required:true,benefits_active:false,
          note:"A solicitação depende da verificação posterior do cadastro."
        })
      }));
      await page.route("**/api/v1/public/programs/loja-jardim/join/",route=>route.fulfill({
        status:202,contentType:"application/json",
        body:JSON.stringify({
          status:"pending_verification",terms_version:"v1",
          participant_created:false,cashback_enabled:false,
          message:"Solicitação recebida. A loja ainda precisa confirmar seu cadastro."
        })
      }));
      await page.goto("/participar/loja-jardim");
      await expect(page.getByText("Programa da Loja Jardim")).toBeVisible();
      await expect(page.getByText("Aviso de privacidade da loja")).toBeVisible();
      await expect(page.getByRole("checkbox",{name:/comunicações promocionais/})).not.toBeChecked();
      await page.getByRole("textbox",{name:"Seu nome"}).fill("Cliente Interessado");
      await page.getByRole("textbox",{name:"Seu e-mail"}).fill("cliente@example.invalid");
      await page.getByRole("checkbox",{name:/Li e aceito os termos/}).check();
      await page.getByRole("button",{name:"Registrar meu aceite"}).click();
      await expect(page.getByRole("heading",{name:"Aceite registrado."})).toBeVisible();
      await expect(page.getByText("não gera saldo, desconto, pontos ou cashback",{exact:false})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth))
        .toBeLessThanOrEqual(1);
    }
  );
}


for(const width of [390,768,1440]){
  test("Confirmar e-mail com token e retirada em "+width+"px", async ({page})=>{
    await page.setViewportSize({width,height:850});
    await page.context().addCookies([{
      name:"csrftoken",value:"csrf-mail-test",url:"http://127.0.0.1:4173"
    }]);
    await page.route("**/api/v1/auth/session/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        authenticated:false,user:null,tenants:[]
      })
    }));
    await page.route("**/api/v1/public/enrollment/email-action/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        status:"email_verified",identity_verified_in_nuvemshop:false,
        participant_created:false,cashback_enabled:false,
        message:"E-mail confirmado. A loja ainda precisa validar o cadastro na Nuvemshop."
      })
    }));
    await page.goto("/confirmar#acao=verify&token="+ "A".repeat(43));
    await expect(page.getByRole("heading",{name:"Confirme seu endereço de e-mail"})).toBeVisible();
    await page.getByRole("button",{name:"Confirmar meu e-mail"}).click();
    await expect(page.getByRole("heading",{name:"E-mail confirmado."})).toBeVisible();
    await expect(page.getByText("não concedeu cashback, pontos ou descontos",{exact:false})).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth))
      .toBeLessThanOrEqual(1);
  });

  test("Solicitar retirada sem revelar existência da conta em "+width+"px",async ({page})=>{
    await page.setViewportSize({width,height:850});
    await page.context().addCookies([{
      name:"csrftoken",value:"csrf-withdraw-test",url:"http://127.0.0.1:4173"
    }]);
    await page.route("**/api/v1/auth/session/",route=>route.fulfill({
      contentType:"application/json",body:JSON.stringify({
        authenticated:false,user:null,tenants:[]
      })
    }));
    await page.route("**/api/v1/public/programs/loja-jardim/withdraw-request/",route=>route.fulfill({
      status:202,contentType:"application/json",body:JSON.stringify({
        status:"accepted",
        message:"Se houver uma solicitação correspondente, enviaremos um link de confirmação."
      })
    }));
    await page.goto("/retirar/loja-jardim");
    await expect(page.getByRole("heading",{name:"Retirar minha solicitação"})).toBeVisible();
    await page.getByRole("textbox",{name:"Seu e-mail"}).fill("cliente@example.invalid");
    await page.getByRole("button",{name:"Solicitar retirada por e-mail"}).click();
    await expect(page.getByText("Se houver uma solicitação associada",{exact:false})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth))
      .toBeLessThanOrEqual(1);
  });
}
