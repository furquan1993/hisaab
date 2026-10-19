// Synthetic credentials arrive only through the isolated test runner's environment.
import { chromium, expect } from "@playwright/test";
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
  await page.getByRole("button", { name: "Details for SYNTHETIC SHOP", exact: true }).click();
  const evidenceTrigger = page.getByRole("button", { name: "View evidence" });
  await evidenceTrigger.click();
  const evidenceHeading = page.getByRole("heading", {
    name: "SYNTHETIC SHOP",
    exact: true,
  });
  await expect(evidenceHeading).toBeFocused();
  await expect(evidenceHeading).toBeInViewport();
  await page
    .getByText("01/01/2026 SYNTHETIC SHOP 123.45", { exact: true })
    .waitFor();
  await page.getByRole("button", { name: "Close evidence" }).click();
  await expect(evidenceTrigger).toBeFocused();
  await page.getByRole("button",{name:"Accounts",exact:true}).click();
  await page.getByLabel("Account name").fill("Synthetic browser pot");
  await page.getByRole("button",{name:"Create Account",exact:true}).click();
  await page.getByRole("button",{name:"Edit Synthetic browser pot"}).waitFor();
  await page.getByRole("button",{name:"Categories",exact:true}).click();
  await page.getByLabel("Category name").fill("Synthetic browser category");
  await page.getByRole("button",{name:"Create Category",exact:true}).click();
  await page.getByRole("button",{name:"Edit Synthetic browser category"}).waitFor();
  await page.getByRole("button",{name:"Statements",exact:true}).click();
  await page.getByRole("button", { name: "Details for SYNTHETIC SHOP", exact: true }).click();
  await page.getByRole("button",{name:"Edit entry",exact:true}).click();
  await page.getByLabel("Account",{exact:true}).selectOption({label:"Synthetic browser pot"});
  await page.getByLabel("Category",{exact:true}).selectOption({label:"Synthetic browser category"});
  await page.getByRole("button",{name:"Save assignments",exact:true}).click();
  await expect(page.getByRole("cell",{name:"Synthetic browser pot",exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole("cell",{name:"Synthetic browser pot",exact:true})).toBeVisible();
  await expect(page.getByRole("cell",{name:"Synthetic browser category",exact:true})).toBeVisible();
  await page.getByRole("button", { name: "Details for SYNTHETIC SHOP", exact: true }).click();
  await page.getByRole("button",{name:"Review entry",exact:true}).click();
  await page.getByLabel("Reviewed description",{exact:true}).fill("SYNTHETIC REVIEWED SHOP");
  await page.getByLabel("Review reason",{exact:true}).fill("Synthetic checked original merchant text");
  await page.getByRole("button",{name:"Save review",exact:true}).click();
  await expect(page.getByText("SYNTHETIC REVIEWED SHOP",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Imports",exact:true}).click();
  await page.getByRole("button",{name:"Review statement",exact:true}).click();
  await page.getByRole("checkbox",{name:/synthetic review/}).check();
  await page.getByLabel("Statement review reason",{exact:true}).fill("Synthetic manually verified full statement coverage");
  await page.getByRole("button",{name:"Save statement review",exact:true}).click();
  await page.getByRole("button",{name:"Review candidate",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Compare statement sources",exact:true})).toBeFocused();
  await page.getByLabel("Revision reason",{exact:true}).fill("Synthetic explicitly reviewed browser revision");
  await page.getByRole("button",{name:"Accept reviewed source",exact:true}).click();
  await expect(page.getByText("Published source updated. Earlier evidence and decisions remain in history.",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Statements",exact:true}).click();
  await expect(page.getByRole("cell",{name:"Synthetic browser pot",exact:true})).toBeVisible();
  await expect(page.getByRole("cell",{name:"Synthetic browser category",exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole("cell",{name:"Synthetic browser pot",exact:true})).toBeVisible();
  await page.getByRole("tab", { name: "Transaction date" }).click();
  await page.getByText("SYNTHETIC REVIEWED SHOP", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).waitFor();
  if (await page.getByText("SYNTHETIC REVIEWED SHOP", { exact: true }).count())
    throw Error("Private row survived sign-out");
  if (failures.length) throw Error("Browser encountered an uncaught error");
  console.log(
    "Real Auth browser smoke passed: login, evidence, assignments, reasoned corrections, coverage review, source revision, persisted reload, date view, logout.",
  );
} finally {
  await browser.close();
}
