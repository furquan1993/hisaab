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
  if (await page.getByRole("button", { name: "Date: filter and sort" }).count() && !(await page.getByLabel("From", { exact: true }).isVisible()))
    await page.getByRole("button", { name: "Date: filter and sort" }).click();
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
  if (await page.getByRole("button", { name: "Date: filter and sort" }).count() && !(await page.getByLabel("From", { exact: true }).isVisible()))
    await page.getByRole("button", { name: "Date: filter and sort" }).click();
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
    return detail;
  }
  let detail = await openFunding("2026-02");
  const feb = detail.getByRole("checkbox", {
    name: "SYNTHETIC FEB SHOP · INR 50.00",
    exact: true,
  });
  await expect(
    detail.getByRole("button", { name: "Settle selected transactions" }),
  ).toBeDisabled();
  await feb.check();
  await expect(
    detail.getByText("Contribution total: INR 50.00", { exact: true }),
  ).toBeVisible();
  await expect(detail.getByLabel("Partial contribution amount")).toHaveCount(0);
  await detail
    .getByLabel("Contribution note (optional)")
    .fill("Synthetic selected transaction contribution");
  await detail
    .getByRole("button", { name: "Settle selected transactions", exact: true })
    .click();
  await expect(
    detail.getByText("Outstanding: INR 100.00", { exact: true }),
  ).toBeVisible();
  await expect(feb).toBeDisabled();
  await expect(
    detail.getByRole("checkbox", {
      name: "SYNTHETIC SHOP · INR 100.00",
      exact: true,
    }),
  ).toBeEnabled();
  await expect(
    detail.getByText("SYNTHETIC FEB SHOP · INR 50.00 · Settled in full", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  detail = await openFunding("2026-02");
  await expect(
    detail.getByRole("checkbox", {
      name: "SYNTHETIC FEB SHOP · INR 50.00",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    detail.getByText("Synthetic selected transaction contribution", {
      exact: true,
    }),
  ).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await detail.scrollIntoViewIfNeeded();
    const box = await detail.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    await page.screenshot({
      path: `/tmp/hisaab-transaction-settlement-${width}.png`,
      fullPage: true,
    });
  }
  await detail
    .getByRole("checkbox", { name: "SYNTHETIC SHOP · INR 100.00", exact: true })
    .check();
  await detail
    .getByRole("button", { name: "Settle selected transactions", exact: true })
    .click();
  await expect(
    detail.getByText("Outstanding: INR 0.00", { exact: true }),
  ).toBeVisible();
  expect(failures).toEqual([]);
  console.log(
    "Selected transaction contributions pass: full amounts, original month, receipt history, reload, desktop and mobile.",
  );
} finally {
  await browser.close();
}
