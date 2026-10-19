// Explicit synthetic demo only, even when the server has live configuration.
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    const page = await browser.newPage({ viewport });
    const failures = [];
    page.on("pageerror", (error) => failures.push(error.message));
    await page.goto("http://127.0.0.1:5183/hisaab/");
    await page.getByRole("button", { name: "Explore synthetic demo" }).click();
    const row = page.locator(".entry-row").filter({
      has: page.getByText("Weekend bookstore", { exact: true }),
    });
    await row.scrollIntoViewIfNeeded();
    expect((await row.boundingBox()).height).toBeLessThanOrEqual(64);
    await expect(
      page.getByRole("button", { name: "View evidence" }),
    ).toHaveCount(0);
    await row.locator(".entry-description").click();
    const details = page.getByRole("region", {
      name: "Details for Weekend bookstore",
      exact: true,
    });
    await expect(details).toBeVisible();
    expect(
      await details.evaluate((el) =>
        el.closest("tr").previousElementSibling.classList.contains("entry-row"),
      ),
    ).toBe(true);
    const scroll = await page.evaluate(() => window.scrollY);
    for (const [action, panel] of [
      ["View evidence", "Source evidence"],
      ["Edit entry", "Entry decisions"],
      ["Review entry", "Entry review"],
    ]) {
      await details.getByRole("button", { name: action, exact: true }).click();
      await expect(
        details.getByRole("complementary", { name: panel, exact: true }),
      ).toBeVisible();
      await expect(details.getByRole("heading", { level: 2 })).toBeFocused();
      await expect(page.getByRole("complementary")).toHaveCount(1);
      expect(
        Math.abs((await page.evaluate(() => window.scrollY)) - scroll),
      ).toBeLessThanOrEqual(2);
      const box = await details.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
    }
    await page.screenshot({ path: `/tmp/hisaab-inline-${viewport.width}.png` });
    await page
      .getByLabel("Reviewed description", { exact: true })
      .fill("Synthetic inline reviewed");
    await page
      .getByLabel("Review reason", { exact: true })
      .fill("Synthetic inline layout verification");
    await page
      .getByRole("button", { name: "Save review", exact: true })
      .click();
    const toggle = page.getByRole("button", {
      name: "Details for Synthetic inline reviewed",
      exact: true,
    });
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("status")).toContainText("Review saved");
    await toggle.press("Enter");
    await expect(page.getByRole("region", { name: /Details for/ })).toHaveCount(
      0,
    );
    await toggle.press("Space");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await page
      .getByRole("tab", { name: "Transaction date", exact: true })
      .click();
    await expect(page.getByRole("region", { name: /Details for/ })).toHaveCount(
      0,
    );
    expect(failures).toEqual([]);
    await page.close();
  }
  console.log(
    "Inline browser checks passed: compact rows, adjacent panels, stable scroll, mobile width, keyboard toggles and save focus.",
  );
} finally {
  await browser.close();
}
