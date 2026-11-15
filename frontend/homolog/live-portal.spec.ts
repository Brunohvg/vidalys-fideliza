import {expect,test} from "@playwright/test";
import {existsSync} from "node:fs";
import {resolve} from "node:path";

const slug=process.env.FIDELIZA_SMOKE_CLUB_SLUG||"";
if(!/^(qa|homolog)-[a-z0-9-]{3,52}$/.test(slug)){
  throw new Error("FIDELIZA_SMOKE_CLUB_SLUG exige tenant QA isolado.");
}
const session=process.env.FIDELIZA_HOMOLOG_STORAGE_STATE||"";
const publicPath="/clube/"+slug;

test("visitante: rota real, catálogo informativo e login separado",async({page})=>{
  const errors:string[]=[];
  page.on("pageerror",err=>errors.push(err.message));
  await page.goto(publicPath,{waitUntil:"domcontentloaded"});
  await expect(page.getByRole("heading",{name:/Mais motivos para voltar/})).toBeVisible();
  await expect(page.getByRole("region",{name:"Entrar no clube"})).toBeVisible();
  const response=await page.request.get("/api/v1/public/clubs/"+slug+"/");
  expect(response.status()).toBe(200);
  const catalog=await response.json();
  expect(catalog.store_slug).toBe(slug);
  expect(catalog.redemption_enabled).toBe(false);
  for(const reward of catalog.published_rewards||[]){
    expect(reward.redemption_enabled).toBe(false);
  }
  expect(errors).toEqual([]);
});

for(const width of [320,390,768]){
  test("participante real: VIP, carteira, resgate bloqueado e histórico "+width+"px",async({browser})=>{
    if(!session || !existsSync(session)){
      throw new Error("Informe FIDELIZA_HOMOLOG_STORAGE_STATE com sessão QA válida em arquivo privado.");
    }
    const context=await browser.newContext({
      baseURL:process.env.FIDELIZA_HOMOLOG_BASE_URL,
      storageState:resolve(session),
      viewport:{width,height:850},
      ignoreHTTPSErrors:false,
    });
    try{
      const page=await context.newPage();
      const errors:string[]=[];
      page.on("pageerror",err=>errors.push(err.message));
      const meResp=await context.request.get("/api/v1/public/clubs/"+slug+"/me/");
      expect(meResp.status(),"Sessão do participante QA não está autenticada").toBe(200);
      const member=await meResp.json();
      expect(member.redemption_enabled).toBe(false);
      expect(member.orders_verified).toBe(false);
      // Conta QA nova, sem concessões; não permitir que UI invente saldo/VIP.
      expect(member.points_balance).toBeNull();
      expect(member.cashback_balance_cents).toBeNull();
      const rewards=member.available_rewards||[];
      expect(rewards.length,"Prepare uma recompensa publicada somente no tenant QA").toBeGreaterThan(0);
      for(const reward of rewards){
        expect(reward.redemption_enabled).toBe(false);
        expect(reward.id).toMatch(/^[a-f0-9-]{36}$/i);
      }
      // POST real usando reward_id: deve falhar fechado sem criar voucher.
      // Conta QA e CSRF reais; não simular APIs nem forjar saldo.
      await context.request.get("/api/v1/auth/session/");
      const csrf=(await context.cookies()).find(c=>c.name==="csrftoken");
      expect(csrf,"CSRF da sessão QA ausente").toBeDefined();
      const rejected=await context.request.post(
        "/api/v1/public/clubs/"+slug+"/vouchers/issue/",
        {
          data:{reward_id:rewards[0].id},
          headers:{
            "X-CSRFToken":csrf!.value,
            "Origin":process.env.FIDELIZA_HOMOLOG_BASE_URL!,
          },
        },
      );
      expect(rejected.status(),"Resgate deve permanecer desligado").toBe(409);
      await page.goto(publicPath,{waitUntil:"domcontentloaded"});
      await expect(page.getByRole("heading",{name:/Olá,/})).toBeVisible();
      const vip=page.getByRole("region",{name:"Meu nível VIP"});
      const wallet=page.getByRole("region",{name:"Resumo da minha carteira"});
      const redeem=page.getByRole("region",{name:"Resgate rápido"});
      const missions=page.getByRole("region",{name:"Missões do clube"});
      for(const region of [vip,wallet,redeem,missions]){
        await expect(region).toBeVisible();
      }
      await expect(redeem.getByRole("button",{name:"Gerar voucher"})).toBeDisabled();
      const boxes=await Promise.all([vip,wallet,redeem,missions].map(r=>r.boundingBox()));
      expect(boxes.every(b=>b!==null)).toBe(true);
      for(let i=1;i<boxes.length;i++){
        expect(boxes[i]!.y).toBeGreaterThan(boxes[i-1]!.y);
      }
      await page.getByRole("navigation",{name:"Seu clube"})
        .getByRole("button",{name:"Histórico"}).click();
      await expect(page).toHaveURL(new RegExp("/clube/"+slug+"/historico$"));
      await expect(page.getByRole("heading",{name:"Histórico de pontos"})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))
        .toBeLessThanOrEqual(1);
      expect(errors).toEqual([]);
    }finally{
      await context.close();
    }
  });
}
