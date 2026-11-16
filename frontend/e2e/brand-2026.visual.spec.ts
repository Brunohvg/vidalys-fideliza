import {test,expect} from "@playwright/test";

test("home e demo usam a marca de fidelização e favicon",async({page})=>{
  await page.goto("/");
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href","/favicon.svg");
  await expect(page.locator(".mk-logo img")).toHaveAttribute("src","/brand-logo.svg");
  await expect(page.locator(".loyalty-home-hero")).toBeVisible();
  await expect(page.locator(".loyalty-home-hero")).toHaveCSS("color","rgb(59, 30, 130)");
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.goto("/demo");
  await expect(page.locator(".brand-mark img")).toHaveAttribute("src","/brand-mark.svg");
});

test("animações decorativas respeitam movimento reduzido",async({page})=>{
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.goto("/");
  const animation=await page.locator(".loyalty-home-gift").evaluate(el=>getComputedStyle(el).animationName);
  expect(animation).toBe("none");
  const behavior=await page.evaluate(()=>getComputedStyle(document.documentElement).scrollBehavior);
  expect(behavior).toBe("auto");
});
