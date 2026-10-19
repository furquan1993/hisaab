// Synthetic demo only; no credentials or private statements are used.
import { chromium, expect } from "@playwright/test";

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto("http://127.0.0.1:5183/hisaab/");
  await page.getByRole("button", { name: "Explore synthetic demo" }).click();
  await page.getByRole("button", { name: "Summary", exact: true }).click();
  const summary = page.getByRole("region", { name: "INR spending summary" });
  await expect(summary.locator(".summary-net strong")).toHaveText("INR 3,832.35");
  await expect(summary.getByText("Net spending this cycle", { exact: true })).toBeVisible();
  const bills = page.getByRole("region", { name: "Statement bills" });
  await expect(bills.getByRole("article")).toHaveCount(4);
  await bills.getByText("How this bill adds up").nth(1).click();
  await expect(bills.getByText("Difference from printed bill").first()).toBeVisible();
  await expect(page.getByText("7 non-payment entries · 1 card payment excluded")).toBeVisible();
  await expect(page.getByRole("table", { name: "By card · INR" }).getByRole("row")).toHaveCount(5);
  await page.screenshot({ path: "/tmp/hisaab-summary-desktop.png", fullPage: true });
  await page.getByLabel("Date basis").selectOption("transaction");
  await expect(bills).toHaveCount(0);
  await expect(summary.getByText("Net spending in month", { exact: true })).toBeVisible();
  await expect(summary.locator(".summary-net strong")).toHaveText("INR 3,904.25");
  await page.getByRole("button", { name: "View entries", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Transaction date" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Filter dates")).toHaveValue("reviewed");
  await expect(page.getByText("Late-posted train ticket", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Summary", exact: true }).click();
  await page.getByRole("button", { name: "Next summary month" }).click();
  await expect(summary.locator(".summary-net strong")).toHaveText("INR 1,380.00");
  await page.getByRole("button", { name: "View reconciliation" }).click();
  await expect(page.getByLabel("Reconciliation month")).toHaveValue("02");
  await page.getByRole("button", { name: "Summary", exact: true }).click();
  await page.getByRole("button", { name: "Previous summary month" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(summary.locator(".summary-net strong")).toHaveText("INR 3,832.35");
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(hasOverflow).toBe(false);
  await page.screenshot({ path: "/tmp/hisaab-summary-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Previous summary month" }).click();
  await expect(page.getByText("No spending entries this month")).toBeVisible();
  expect(failures).toEqual([]);
  console.log("Summary browser checks passed at desktop and mobile sizes.");
} finally {
  await browser.close();
}
