import {expect,test} from "@playwright/test";

const assets=["/favicon.svg","/brand-logo.svg","/brand-logo-white.svg","/brand-mark.svg","/loyalty-gift.svg"];
test("arquivos públicos da identidade respondem com SVG válido",async({request})=>{
 for(const asset of assets){
  const res=await request.get(asset);
  expect(res.ok(),asset).toBeTruthy();
  const body=await res.text();
  expect(body,asset).toMatch(/<svg\b/);
  expect(body,asset).toContain("</svg>");
 }
});
for(const width of [320,390,768,1440]){
 test("home premium sem corte horizontal em "+width+"px",async({page},info)=>{
  await page.setViewportSize({width,height:850});
  await page.goto("/");
  await expect(page.locator(".loyalty-home-hero")).toBeVisible();
  await expect(page.locator(".loyalty-home-gift")).toBeVisible();
  await expect(page.getByRole("heading",{level:1,name:/Seus clientes sempre voltam/})).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath("brand-home-"+width+".png"),fullPage:true});
 });
}
test("manifesto, favicon e identidade acessíveis",async({request,page})=>{
 const res=await request.get("/site.webmanifest");
 expect(res.ok()).toBeTruthy();
 const manifest=await res.json();
 expect(manifest.name).toBe("Vidalys Fideliza");
 await page.goto("/");
 await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href","/site.webmanifest");
 await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href","/favicon.svg");
});

test("tokens de marca permanecem iguais entre home, demo e acesso",async({page})=>{
 const readTokens=async()=>{
  return await page.evaluate(()=>{
   const style=getComputedStyle(document.documentElement);
   return {
    primary:style.getPropertyValue("--vf-primary").trim(),
    reward:style.getPropertyValue("--vf-reward").trim(),
    canvas:style.getPropertyValue("--vf-canvas").trim(),
    purple:style.getPropertyValue("--vf-purple-900").trim()
   };
  });
 };
 await page.goto("/");
 const home=await readTokens();
 expect(home).toEqual({primary:"#6A3DF0",reward:"#FFC857",canvas:"#F8F9FF",purple:"#3B1E82"});
 await page.goto("/demo");
 expect(await readTokens()).toEqual(home);
 await page.goto("/entrar");
 expect(await readTokens()).toEqual(home);
});
