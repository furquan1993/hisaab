// Actual local Auth and synthetic transactions, never private statement records.
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(process.env.HISAAB_E2E_BASE_URL);
  await page
    .getByLabel("Email", { exact: true })
    .fill(process.env.HISAAB_E2E_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.HISAAB_E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByText("SYNTHETIC TRIP HOTEL", { exact: true }).waitFor();
  await page.getByLabel("From", { exact: true }).waitFor({ state: "attached" });
  if (await page.locator(".column-date-range:not([open]) > summary").count())
    await page.locator(".column-date-range > summary").click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-01");
  await page.getByText("SYNTHETIC SHOP", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Categories", exact: true }).click();
  await page.getByLabel("Category name").fill("Travel");
  await page
    .getByRole("button", { name: "Create Category", exact: true })
    .click();
  await page.getByRole("button", { name: "Statements", exact: true }).click();
  await page
    .getByLabel("Category for SYNTHETIC SHOP", { exact: true })
    .selectOption({ label: "Travel" });
  await page.getByRole("button", { name: "Spending", exact: true }).click();
  await page.getByRole("button", { name: "+ New group", exact: true }).click();
  await page.getByLabel("Group name").fill("Goa trip");
  await page.getByRole("button", { name: "Create group", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Goa trip", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add / move entries", exact: true })
    .click();
  for (const name of [
    "SYNTHETIC SHOP",
    "SYNTHETIC TRIP REFUND",
    "SYNTHETIC TRIP HOTEL",
  ]) {
    await page
      .getByRole("checkbox", { name: `Select ${name}`, exact: true })
      .check();
  }
  await page
    .getByRole("button", { name: "Save 3 assignments", exact: true })
    .click();
  await expect(page.locator(".spending-net")).toHaveText("INR 300.00");
  await expect(
    page.getByText("3 entries across 2 cards", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^Travel/ }).click();
  await expect(
    page.locator(".spending-detail .spending-entry-list > li"),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "Clear filter", exact: true }).click();
  await page.getByLabel("Spending period").selectOption("2026-02");
  await expect(page.locator(".spending-net")).toHaveText("INR 200.00");
  await page.reload();
  await page.getByRole("button", { name: "Spending", exact: true }).click();
  await expect(page.locator(".spending-net")).toHaveText("INR 300.00");
  await page.getByRole("button", { name: "Statements", exact: true }).click();
  await page.getByLabel("From", { exact: true }).waitFor({ state: "attached" });
  if (await page.locator(".column-date-range:not([open]) > summary").count())
    await page.locator(".column-date-range > summary").click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-01");
  await page
    .getByRole("button", { name: "Details for SYNTHETIC SHOP", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Assign trip or group", exact: true })
    .click();
  await expect(page.getByLabel("Entry trip or group")).toHaveValue(
    await page
      .getByLabel("Entry trip or group")
      .getByRole("option", { name: "Goa trip", exact: true })
      .getAttribute("value"),
  );
  await page.getByLabel("Entry trip or group").selectOption("");
  await page
    .getByRole("button", { name: "Save trip assignment", exact: true })
    .click();
  await page.getByRole("button", { name: "Spending", exact: true }).click();
  await expect(page.locator(".spending-net")).toHaveText("INR 176.55");
  await expect(
    page.getByRole("button", { name: "Spending", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.mouse.move(1400, 10);
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `/tmp/hisaab-spending-app-${width}.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
  console.log(
    "Spending browser checks passed: cross-card groups, refunds, categories, months, reload persistence, Statements assignment and mobile layout.",
  );
} finally {
  await browser.close();
}
