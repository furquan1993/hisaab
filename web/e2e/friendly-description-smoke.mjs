// Actual local Auth/API with synthetic records, desktop and mobile.
import { chromium, expect } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
const browser = await chromium.launch();
try {
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://127.0.0.1:5183/hisaab/");
    await page
      .getByLabel("Email", { exact: true })
      .fill(process.env.HISAAB_E2E_EMAIL);
    await page
      .getByLabel("Password", { exact: true })
      .fill(process.env.HISAAB_E2E_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    const title = page.locator(".entry-description").first();
    await expect(title).toBeVisible();
    const original = await title.textContent();
    await title.click();
    await page
      .getByRole("button", { name: "Edit description", exact: true })
      .click();
    const editor = page.getByRole("complementary", {
      name: "Friendly description editor",
    });
    await expect(editor.getByRole("heading")).toBeFocused();
    await editor
      .getByLabel("Friendly description", { exact: true })
      .fill("Desk lamp from Amazon");
    await editor.getByRole("button", { name: "Save description" }).click();
    await expect(title).toHaveText("Desk lamp from Amazon");
    await expect(
      page.getByText(`Statement: ${original}`, { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: join(tmpdir(), `hisaab-friendly-${viewport.width}.png`),
      fullPage: true,
    });
    await page.reload();
    await expect(title).toHaveText("Desk lamp from Amazon");
    const search = page.getByLabel("Search descriptions");
    await search.fill("Desk lamp");
    await expect(page.locator(".entry-description")).toHaveText([
      "Desk lamp from Amazon",
    ]);
    await search.fill(original);
    await expect(page.locator(".entry-description")).toHaveText([
      "Desk lamp from Amazon",
    ]);
    await search.fill("No such purchase 98765");
    await expect(
      page.getByRole("heading", { name: "No matching entries" }),
    ).toBeVisible();
    await search.fill("");
    await expect(title).toHaveText("Desk lamp from Amazon");
    await title.click();
    await page
      .getByRole("button", { name: "Edit description", exact: true })
      .click();
    await editor.getByLabel("Friendly description", { exact: true }).fill("");
    await editor.getByRole("button", { name: "Save description" }).click();
    await expect(title).toHaveText(original);
    await page.reload();
    await expect(title).toHaveText(original);
    expect(errors).toEqual([]);
    await page.close();
  }
  console.log(
    "Friendly descriptions: save, reload, search both descriptions and clear pass on desktop and mobile.",
  );
} finally {
  await browser.close();
}
