import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(process.env.HISAAB_WEB_URL ?? "http://127.0.0.1:5183/hisaab/");
    await page.getByRole("button", { name: "Explore synthetic demo" }).click();
    await page.getByRole("button", { name: "Cards", exact: true }).click();
    await page.getByLabel("Card name", { exact: true }).fill("New everyday card");
    await page.getByLabel("Bank", { exact: true }).selectOption("sbi");
    await page.getByLabel("Last four digits (optional)").fill("0042");
    await page.getByRole("button", { name: "Add card", exact: true }).click();
    await expect(page.getByRole("button", { name: "Edit New everyday card", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edit New everyday card", exact: true }).click();
    await page.getByLabel("Card name", { exact: true }).fill("Renamed everyday card");
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await page.getByRole("button", { name: "Statements", exact: true }).click();
    await page.getByRole("button", { name: "Cards", exact: true }).click();
    await expect(page.getByRole("button", { name: "Edit Renamed everyday card", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edit Regalia • demo", exact: true }).click();
    await expect(page.getByLabel("Bank", { exact: true })).toBeDisabled();
    await page.getByLabel("Card name", { exact: true }).fill("Renamed Regalia");
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await page.screenshot({ path: `/tmp/hisaab-cards-${viewport.width}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Statements", exact: true }).click();
    await expect(page.getByText("Renamed Regalia", { exact: true }).first()).toBeVisible();
    expect(errors).toEqual([]);
    await page.close();
  }
  console.log("Cards pass desktop/mobile create, edit, session persistence, bank lock and renamed statements.");
} finally { await browser.close(); }
