// Synthetic demo: confirmation, cancel, unassignment and responsive dialog.
import { chromium, expect } from "@playwright/test";
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
    await page.getByRole("button", { name: "Explore synthetic demo" }).click();
    await page.getByRole("button", { name: "Accounts", exact: true }).click();
    await page
      .getByLabel("Account name", { exact: true })
      .fill("Deletion test pot");
    await page
      .getByRole("button", { name: "Create Account", exact: true })
      .click();
    await expect(
      page.getByText("Account saved.", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Statements", exact: true }).click();
    const account = page.getByLabel("Account for Weekend bookstore", {
      exact: true,
    });
    await account.selectOption({ label: "Deletion test pot" });
    await page.getByRole("button", { name: "Accounts", exact: true }).click();
    await page
      .getByRole("button", { name: "Delete Deletion test pot", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Delete Deletion test pot?",
    });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText("Weekend bookstore", { exact: true }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    const bounds = await dialog.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width + 1);
    await page.screenshot({ path: `/tmp/hisaab-delete-${viewport.width}.png` });
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByRole("button", {
        name: "Delete Deletion test pot",
        exact: true,
      }),
    ).toBeFocused();
    await page
      .getByRole("button", { name: "Delete Deletion test pot", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "Delete account and unassign transactions" })
      .click();
    await expect(page.getByRole("status")).toHaveText(
      "Account deleted. Its transactions are now unassigned.",
    );
    await expect(
      page.getByRole("button", {
        name: "Delete Deletion test pot",
        exact: true,
      }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Statements", exact: true }).click();
    await expect(account).toHaveValue("");
    expect(errors).toEqual([]);
    await page.close();
  }
  console.log(
    "Account deletion passes on desktop and mobile: preview, cancel, confirm and unassignment.",
  );
} finally {
  await browser.close();
}
