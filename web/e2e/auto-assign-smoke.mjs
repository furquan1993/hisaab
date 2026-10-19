// Synthetic credentials are supplied by the isolated local test runner only.
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto("http://127.0.0.1:5183/hisaab/");
  await page.getByLabel("Email", { exact: true }).fill(process.env.HISAAB_E2E_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(process.env.HISAAB_E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const account = page.getByLabel("Account for SWIGGY INSTAMART", { exact: true });
  const category = page.getByLabel("Category for SWIGGY INSTAMART", { exact: true });
  await expect(account.locator("option:checked")).toHaveText("Synthetic history account");
  await expect(category.locator("option:checked")).toHaveText("Groceries");
  await page.reload();
  await expect(account.locator("option:checked")).toHaveText("Synthetic history account");
  await account.selectOption("");
  await expect(account).toBeEnabled();
  await page.reload();
  await expect(account.locator("option:checked")).toHaveText("Unassigned");
  await expect(category.locator("option:checked")).toHaveText("Groceries");
  expect(failures).toEqual([]);
  console.log("Automatic assignment browser check passed: history account, starter category, reload persistence and protected manual removal.");
} finally {
  await browser.close();
}
