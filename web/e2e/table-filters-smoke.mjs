// Synthetic data only. Check compact, consistent menus on every data column.
import { chromium, expect } from "@playwright/test";
const browser = await chromium.launch();
try {
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const failures=[];
    page.on("pageerror",error=>failures.push(error.message));
    await page.route("**/*",route=>["localhost","127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    await page.goto(process.env.HISAAB_E2E_BASE_URL ?? "http://127.0.0.1:5183/hisaab/");
    await page.getByRole("button",{name:"Explore synthetic demo"}).click();
    const table=page.locator(".statement-table");
    await expect(table.locator(".entry-row").first()).toBeVisible();
    async function open(title) {
      await page.getByRole("button",{name:`${title}: filter and sort`,exact:true}).click();
      const panel=page.getByLabel(`${title} options`,{exact:true});
      await expect(panel).toBeVisible();
      const box=await panel.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x+box.width).toBeLessThanOrEqual(viewport.width);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);
      return panel;
    }
    for (const title of ["Transaction","Card & statement","Date","Type","Account","Category","Amount"]) {
      await open(title);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("button",{name:`${title}: filter and sort`,exact:true})).toBeFocused();
    }
    await open("Transaction");
    const description=await table.locator(".entry-description").first().textContent();
    await page.getByLabel("Search descriptions").fill(description);
    await expect(table.locator(".entry-description").first()).toHaveText(description);
    await page.getByLabel("Search descriptions").clear();
    await page.keyboard.press("Escape");
    await open("Card & statement");
    await page.getByLabel("Filter by card").fill("Regalia");
    await expect(table.locator(".entry-row").first().locator(".card-label")).toContainText("Regalia");
    await page.getByRole("button",{name:"Clear card filter",exact:true}).click();
    await page.keyboard.press("Escape");
    await open("Type");
    await page.getByLabel("Filter by type").selectOption("purchase");
    await expect(table.locator(".entry-row .type").first()).toHaveText("purchase");
    await expect(table.locator(".entry-row .type:not(.purchase)")).toHaveCount(0);
    await page.getByRole("button",{name:"Clear type filter",exact:true}).click();
    await page.keyboard.press("Escape");
    await open("Amount");
    await page.getByLabel("Minimum amount").fill("100");
    await page.getByLabel("Maximum amount").fill("1000");
    await page.getByRole("button",{name:"Largest amount first",exact:true}).click();
    await expect(table.locator('th[aria-sort="descending"]')).toHaveCount(1);
    await page.screenshot({path:`/tmp/hisaab-column-menu-${viewport.width}.png`,fullPage:true});
    await page.getByRole("button",{name:"Clear amount filter",exact:true}).click();
    await page.keyboard.press("Escape");
    await open("Date");
    await page.getByLabel("Sort by transaction date").selectOption("oldest");
    await page.getByLabel("From",{exact:true}).fill("2026-01-01");
    await page.getByLabel("To",{exact:true}).fill("2026-01-31");
    await page.keyboard.press("Escape");
    await expect(table.locator("thead input:not([type=checkbox]):visible, thead select:visible")).toHaveCount(0);
    expect((await table.locator("thead").boundingBox()).height).toBeLessThan(65);
    await page.locator(".table-scroll").evaluate(element=>element.scrollLeft=0);
    await page.screenshot({path:`/tmp/hisaab-table-filters-${viewport.width}.png`,fullPage:true});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    expect(failures).toEqual([]);
    await page.close();
  }
  console.log("All column menus, exact amount filtering, keyboard dismissal and compact desktop/mobile layout passed.");
} finally {await browser.close();}
