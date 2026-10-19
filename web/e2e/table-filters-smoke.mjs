// Synthetic demo only. Column controls work in a horizontally scrolling table.
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const failures = [];
    page.on("pageerror", error => failures.push(error.message));
    await page.route("**/*", route => {
      if (["localhost","127.0.0.1"].includes(new URL(route.request().url()).hostname)) return route.continue();
      failures.push("Nonlocal request in synthetic demo test");
      return route.abort();
    });
    await page.goto(process.env.HISAAB_E2E_BASE_URL ?? "http://127.0.0.1:5183/hisaab/");
    await page.getByRole("button",{name:"Explore synthetic demo"}).click();
    const table = page.locator(".statement-table");
    await expect(table.locator(".entry-row").first()).toBeVisible();
    await expect(page.locator(".statement-filters input, .statement-filters select")).toHaveCount(0);
    for (const name of ["Search descriptions","Filter by account","Filter by category","Sort by transaction date"]) {
      expect(await table.getByLabel(name,{exact:true}).evaluate(element => !!element.closest("th"))).toBe(true);
    }
    const description = await table.locator(".entry-description").first().textContent();
    await table.getByLabel("Search descriptions").fill(description);
    await expect(table.locator(".entry-description").first()).toHaveText(description);
    for (const value of await table.locator(".entry-description").allTextContents()) expect(value).toContain(description);
    await table.getByLabel("Search descriptions").clear();
    await table.getByLabel("Filter by account").selectOption("unassigned");
    await table.getByLabel("Filter by category").selectOption("unassigned");
    await table.getByLabel("Filter by account").selectOption("");
    await table.getByLabel("Filter by category").selectOption("");
    await table.getByLabel("Sort by transaction date").selectOption("oldest");
    await expect(table.locator('th[aria-sort="ascending"]')).toHaveCount(1);
    await table.locator(".column-date-range summary").click();
    await expect(table.getByLabel("From",{exact:true})).toBeVisible();
    await table.getByLabel("From",{exact:true}).fill("2026-01-01");
    await table.getByLabel("To",{exact:true}).fill("2026-01-31");
    await table.locator(".column-date-range summary").click();
    await page.screenshot({path:`/tmp/hisaab-table-filters-${viewport.width}.png`,fullPage:true});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("tab",{name:"Needs review",exact:true}).click();
    await table.locator(".column-date-range summary").click();
    await expect(table.getByLabel("From",{exact:true})).toBeDisabled();
    await expect(table.getByLabel("Filter dates",{exact:true})).toBeDisabled();
    expect(failures).toEqual([]);
    await page.close();
  }
  console.log("Table header search, assignment filters, date sort/range, review restrictions and desktop/mobile layout passed.");
} finally { await browser.close(); }
