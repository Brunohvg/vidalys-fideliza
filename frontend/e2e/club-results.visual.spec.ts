import {expect,test,type Page} from "@playwright/test";

/* Resultados: o que o clube trouxe, com período 30/90, gerado x usado, para onde foi o saldo
   e balcão clube x fora. Dados sintéticos; a tela não afirma causa sem grupo de comparação. */

const tenant={id:"5a1e7c2d-3333-4b3c-8d4e-5f6a7b8c9d0e",name:"Loja Resultado",slug:"loja-resultado",status:"active",role:"owner",platform:"independent"};
const json=(body:unknown)=>({status:200,contentType:"application/json",body:JSON.stringify(body)});
const months=["2026-06-01","2026-07-01","2026-08-01","2026-09-01","2026-10-01","2026-11-01"];
const results=(days:number,gift=true)=>({days,program:gift?{mode:"giftback",percent_bps:1000,cap_cents:2000,min_order_cents:8000,validity_days:30,hold_days:7}:{mode:"points"},
  members_active:48,purchases:days===30?37:96,revenue_cents:days===30?583400:1490200,buyers:days===30?29:61,came_back:days===30?11:27,
  issued:days===30?52300:131000,used:days===30?18700:61200,expired:days===30?2100:9800,reversed:days===30?900:2400,
  discount_cents:days===30?18700:61200,pulled_revenue_cents:days===30?214500:690300,cost_bps:days===30?321:411,
  open:{pending:12400,available:20800,reserved:3500},
  months:months.map((m,i)=>({month:m,issued:[0,0,8000,24100,41000,52300][i],used:[0,0,0,6200,15800,18700][i]})),
  counter:{sales:58,with_member:31,member_cents:401200,other_cents:288900},causal_claim:false});

async function merchant(page:Page,empty=false,gift=true){
  await page.route("**/api/v1/auth/session/",r=>r.fulfill(json({authenticated:true,user:{username:"qa",display_name:"QA"},tenants:[tenant]})));
  await page.route("**/api/v1/tenants/**/participants/**",r=>r.fulfill(json({source:"verified_opt_in_only",data_status:"consent_verified",
    summary:{total:2,active:2,paused:0},total_filtered:2,limit:20,offset:0,
    items:[{id:"p1",display_name:"Ana",joined_at:"2026-10-03T12:00:00Z",consented_at:"2026-10-03T12:00:00Z"},
      {id:"p2",display_name:"Bia",joined_at:"2026-11-02T12:00:00Z",consented_at:"2026-11-02T12:00:00Z"}]})));
  await page.route("**/api/v1/tenants/**/loyalty/results/**",r=>{
    const days=Number(new URL(r.request().url()).searchParams.get("days"))||30;
    const body=results(days,gift);
    if(empty)Object.assign(body,{purchases:0,revenue_cents:0,buyers:0,came_back:0,issued:0,used:0,expired:0,reversed:0,
      discount_cents:0,pulled_revenue_cents:0,cost_bps:null,open:{pending:0,available:0,reserved:0}});
    return r.fulfill(json(body));
  });
}
const go=async(page:Page,width:number)=>{
  await page.goto("/app/visao-geral");
  if(width<=1020)await page.getByRole("button",{name:"Abrir menu"}).click();
  await page.locator("#portal-sidebar").getByRole("button",{name:/^Resultados/}).click();
};
const noOverflow=async(page:Page)=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);

for(const width of [390,768,1440]){
  test("Resultados do clube em "+width+"px: números reais, gráficos com legenda e tabela, sem afirmar causa",async({page},info)=>{
    await page.setViewportSize({width,height:width===390?844:900});await merchant(page);await go(page,width);
    await expect(page.getByRole("heading",{level:1,name:"O que o clube trouxe"})).toBeVisible();
    await expect(page.locator(".vr-kpi")).toHaveCount(4);
    await expect(page.locator(".vr-kpi").first()).toContainText("R$ 5,8 mil");
    await expect(page.locator(".vr-kpi").nth(1)).toContainText("38% compraram mais de uma vez");
    await expect(page.locator(".vr-kpi").nth(2)).toContainText("custo real: 3,21%");
    await expect(page.locator(".vr-kpi").nth(3)).toContainText("Crédito com as clientes");
    await expect(page.getByRole("heading",{name:"Crédito gerado e usado"})).toBeVisible();
    await expect(page.getByRole("table",{name:"Gerado e usado por mês"})).toHaveCount(1);
    await expect(page.getByRole("heading",{name:"Para onde foi o crédito do período"})).toBeVisible();
    await expect(page.locator(".vr-flow").first().locator("li")).toHaveCount(4);
    await expect(page.getByText("Compras em que a cliente usou crédito somaram")).toBeVisible();
    await expect(page.getByRole("heading",{name:"Balcão: clube e fora do clube"})).toBeVisible();
    await expect(page.getByText("não provam que o clube causou as vendas")).toBeVisible();
    await noOverflow(page);
    await page.screenshot({path:info.outputPath("resultados-"+width+".png"),fullPage:true});
  });
}

test("Resultados: trocar para 90 dias recarrega e mostra dica no hover do mês",async({page})=>{
  await page.setViewportSize({width:1440,height:900});await merchant(page);await go(page,1440);
  await expect(page.locator(".vr-kpi").first()).toContainText("37 compras");
  await page.getByRole("button",{name:"90 dias"}).click();
  await expect(page.getByRole("button",{name:"90 dias"})).toHaveAttribute("aria-pressed","true");
  await expect(page.locator(".vr-kpi").first()).toContainText("96 compras");
  await page.locator(".vr-month").last().hover();
  await expect(page.getByRole("tooltip")).toContainText("Usado R$ 187,00");
});

test("Resultados em pontos mostra pts e sem compras mostra o próximo passo",async({page},info)=>{
  await page.setViewportSize({width:390,height:844});await merchant(page,true,false);await go(page,390);
  await expect(page.getByText("Ainda não há compras do clube nos últimos 30 dias")).toBeVisible();
  await expect(page.locator(".vr-kpi").nth(3)).toContainText("Saldo com as clientes");
  await expect(page.locator(".vr-kpi").nth(3)).toContainText("0");
  await page.getByRole("button",{name:"Abrir Meu clube"}).isVisible();
  await noOverflow(page);
  await page.screenshot({path:info.outputPath("resultados-vazio-390.png"),fullPage:true});
});
