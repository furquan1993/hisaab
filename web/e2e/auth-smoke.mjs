// Synthetic credentials arrive only through the isolated test runner's environment.
import { chromium } from "@playwright/test";
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto("http://127.0.0.1:5183/hisaab/");
  await page
    .getByLabel("Email", { exact: true })
    .fill(process.env.HISAAB_E2E_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.HISAAB_E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByText("SYNTHETIC SHOP", { exact: true }).waitFor();
  await page.reload();
  await page.getByText("SYNTHETIC SHOP", { exact: true }).waitFor();
  await page.getByRole("button", { name: "View evidence" }).click();
  await page
    .getByText("01/01/2026 SYNTHETIC SHOP 123.45", { exact: true })
    .waitFor();
  await page.getByRole("tab", { name: "Transaction date" }).click();
  await page.getByText("SYNTHETIC SHOP", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).waitFor();
  if (await page.getByText("SYNTHETIC SHOP", { exact: true }).count())
    throw Error("Private row survived sign-out");
  if (failures.length) throw Error("Browser encountered an uncaught error");
  console.log(
    "Real Auth browser smoke passed: login, reload, evidence, date view, logout.",
  );
} finally {
  await browser.close();
}
