// Only the isolated fixture supplies credentials and synthetic financial records.
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.route("**/*", (route) => {
    if (
      ["127.0.0.1", "localhost"].includes(
        new URL(route.request().url()).hostname,
      )
    )
      return route.continue();
    failures.push("Browser test attempted a nonlocal request");
    return route.abort();
  });
  await page.goto(process.env.HISAAB_E2E_BASE_URL);
  await page
    .getByLabel("Email", { exact: true })
    .fill(process.env.HISAAB_E2E_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.HISAAB_E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("From", { exact: true }).waitFor({ state: "attached" });
  if (await page.locator(".column-date-range:not([open]) > summary").count())
    await page.locator(".column-date-range > summary").click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-01");
  await page.getByLabel("To", { exact: true }).fill("2026-02-28");
  await page.getByText("SYNTHETIC FEB SHOP", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Accounts", exact: true }).click();
  await page.getByLabel("Account name").fill("Synthetic funding");
  await page
    .getByRole("button", { name: "Create Account", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Edit Synthetic funding", exact: true })
    .waitFor();
  await page.getByRole("button", { name: "Statements", exact: true }).click();
  await page.getByLabel("From", { exact: true }).waitFor({ state: "attached" });
  if (await page.locator(".column-date-range:not([open]) > summary").count())
    await page.locator(".column-date-range > summary").click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-01");
  for (const name of ["SYNTHETIC SHOP", "SYNTHETIC FEB SHOP"]) {
    await page
      .getByRole("button", { name: "Details for " + name, exact: true })
      .click();
    await page.getByRole("button", { name: "Edit entry", exact: true }).click();
    await page
      .getByLabel("Account", { exact: true })
      .selectOption({ label: "Synthetic funding" });
    await page
      .getByRole("button", { name: "Save assignments", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Details for " + name, exact: true }),
    ).toBeFocused();
  }
  async function openFunding(month, balanceMonth = month) {
    await page
      .getByRole("button", { name: "Reconciliation", exact: true })
      .click();
    await page.getByLabel("Reconciliation year").fill(month.slice(0, 4));
    await page
      .getByLabel("Reconciliation month")
      .selectOption(month.slice(5, 7));
    await page
      .getByRole("button", {
        name: "View cards for Synthetic funding (INR)",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", {
        name: "Contributions for Invented card · " + balanceMonth,
        exact: true,
      })
      .click();
    const detail = page.getByRole("region", {
      name: "Contributions and balances",
      exact: true,
    });
    await expect(detail.getByRole("table")).toBeVisible();
    await detail.getByLabel("Contribute towards").selectOption("month");
    return detail;
  }
  let detail = await openFunding("2026-01");
  await page.getByText("Included entries · 2026-01", { exact: true }).click();
  await expect(
    page
      .getByRole("list", { name: "Included entries" })
      .getByText("SYNTHETIC SHOP", { exact: true }),
  ).toBeVisible();
  await detail.getByLabel("Partial contribution amount").fill("60");
  await detail
    .getByRole("button", { name: "Record partial contribution", exact: true })
    .click();
  await expect(
    detail.getByText("Outstanding: INR 40.00", { exact: true }),
  ).toBeVisible();
  await page.reload();
  detail = await openFunding("2026-02");
  await expect(
    detail.getByText("Outstanding: INR 90.00", { exact: true }),
  ).toBeVisible();
  await detail.getByLabel("Partial contribution amount").fill("65");
  await detail
    .getByRole("button", { name: "Record partial contribution", exact: true })
    .click();
  await expect(
    detail.getByText("2026-01: INR 40.00", { exact: true }),
  ).toBeVisible();
  await expect(
    detail.getByText("2026-02: INR 25.00", { exact: true }),
  ).toBeVisible();
  await expect(
    detail.getByText("Outstanding: INR 25.00", { exact: true }),
  ).toBeVisible();
  await detail
    .getByRole("button", { name: "Settle in full", exact: true })
    .click();
  await expect(
    detail.getByText("Outstanding: INR 0.00", { exact: true }),
  ).toBeVisible();
  await page.reload();
  detail = await openFunding("2026-02");
  await expect(detail.getByText("Settled", { exact: true })).toHaveCount(2);
  await page.getByRole("button", { name: "Statements", exact: true }).click();
  await page.getByLabel("From", { exact: true }).waitFor({ state: "attached" });
  if (await page.locator(".column-date-range:not([open]) > summary").count())
    await page.locator(".column-date-range > summary").click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-01");
  await page
    .getByRole("button", { name: "Details for SYNTHETIC SHOP", exact: true })
    .click();
  await page.getByRole("button", { name: "Review entry", exact: true }).click();
  await page.getByLabel("Reviewed amount", { exact: true }).fill("120.00");
  await page
    .getByLabel("Review reason", { exact: true })
    .fill("Synthetic corrected statement amount");
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Details for SYNTHETIC SHOP",
      exact: true,
    }),
  ).toBeFocused();
  detail = await openFunding("2026-02");
  await expect(detail.getByText("Needs review", { exact: true })).toBeVisible();
  await expect(
    detail.getByRole("button", { name: "Settle in full", exact: true }),
  ).toBeDisabled();
  await detail
    .getByLabel("Balance review reason")
    .fill("Synthetic verified revised January balance");
  await detail
    .getByRole("button", { name: "Confirm 2026-01", exact: true })
    .click();
  await expect(
    detail.getByRole("button", { name: "Settle in full", exact: true }),
  ).toBeEnabled();
  await detail
    .getByRole("button", { name: "Settle in full", exact: true })
    .click();
  await expect(
    detail.getByText("2026-01: INR 20.00", { exact: true }),
  ).toBeVisible();
  await expect(
    detail.getByText("Outstanding: INR 0.00", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/hisaab-funding-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await detail.scrollIntoViewIfNeeded();
  const box = await detail.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(391);
  await page.screenshot({
    path: "/tmp/hisaab-funding-mobile.png",
    fullPage: true,
  });
  expect(failures).toEqual([]);
  console.log(
    "Funding browser checks passed: partial/full, oldest-month attribution, reload, correction, reconfirmation and mobile layout.",
  );
} finally {
  await browser.close();
}
