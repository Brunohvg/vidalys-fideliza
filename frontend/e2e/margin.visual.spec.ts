import { expect, test } from "@playwright/test";

for (const width of [390, 768, 1440]) {
  test("Rentabilidade funciona no viewport de " + width + "px", async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.goto("/demo");
    const mobile = width <= 980;
    if (mobile) await page.getByRole("button", { name: "Abrir menu" }).click();
    await page.getByRole("button", { name: "Rentabilidade", exact: true }).click();
    if (mobile) {
      // Aguardar a transição do drawer antes de capturar screenshot.
      await expect(page.locator(".sidebar")).not.toHaveClass(/open/);
      await expect.poll(() => page.locator(".sidebar").evaluate(
        element => element.getBoundingClientRect().right
      )).toBeLessThan(2);
    }

    await expect(page.getByRole("heading", { name: "Simulador de rentabilidade" })).toBeVisible();
    await expect(page.getByText("Dentro da meta simulada")).toBeVisible();
    await expect(page.getByText("Cálculos locais com dados digitados")).toBeVisible();

    const noOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth <= window.innerWidth + 1
    );
    const overflowElements = await page.evaluate(() =>
      [...document.body.querySelectorAll("*")].map(el => {
        const rect = el.getBoundingClientRect();
        return { tag: el.tagName, className: String(el.className).slice(0, 90), right: Math.round(rect.right) };
      }).filter(x => x.right > window.innerWidth + 1).slice(0, 12)
    );
    expect(noOverflow, JSON.stringify(overflowElements)).toBe(true);

    await page.screenshot({ path: testInfo.outputPath("margin-default-" + width + ".png"), fullPage: true });

    await page.getByRole("button", { name: "Cashback arriscado" }).click();
    await expect(page.getByText("Cashback acima do limite")).toBeVisible();
    await page.getByRole("button", { name: "Custo ausente" }).click();
    await expect(page.getByText("Custo desconhecido")).toBeVisible();
    await expect(page.getByText("Indisponível").first()).toBeVisible();

    await page.screenshot({ path: testInfo.outputPath("margin-unknown-cost-" + width + ".png"), fullPage: true });
    await page.getByRole("button", { name: "Margem saudável" }).click();
    await expect(page.getByText("Dentro da meta simulada")).toBeVisible();
  });
}
