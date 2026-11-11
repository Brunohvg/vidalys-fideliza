import { expect, test } from "@playwright/test";

for (const width of [390, 768, 1440]) {
  test("Rentabilidade funciona no viewport de " + width + "px", async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.goto("/");
    const mobile = width <= 980;
    if (mobile) await page.getByRole("button", { name: "Abrir menu" }).click();
    await page.getByRole("button", { name: "Rentabilidade", exact: true }).click();

    await expect(page.getByRole("heading", { name: "Simulador de rentabilidade" })).toBeVisible();
    await expect(page.getByText("Dentro da meta simulada")).toBeVisible();
    await expect(page.getByText("Cálculos locais com dados digitados")).toBeVisible();

    const noOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth <= window.innerWidth + 1
    );
    expect(noOverflow).toBe(true);

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
