import { expect, Page, test } from "@playwright/test";

import { signIn, unique } from "./helpers";

async function addItem(page: Page, title: string, extra?: (page: Page) => Promise<void>) {
  await page.goto("/items/new");
  await page.locator("#qs-text").fill(title);
  await page.getByRole("button", { name: "Fill in the form" }).click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  if (extra) await extra(page);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

test("needs attention, sorting by value, selecting several, and duplicating", async ({ page }) => {
  const tag = unique("qol").replace(/\s/g, "");
  const eagle = `2023 American Silver Eagle ${tag}`;
  const bare = `Mystery token ${tag}`;
  await signIn(page);
  await addItem(page, eagle, async (p) => { await p.getByLabel("Price paid (total for all pieces)").fill("40"); });
  await expect(page.getByText("Still to add: photos, value.")).toBeVisible(); // no spot price in this test server, so no value yet
  await page.goto("/items/new");
  await page.getByLabel("Title", { exact: true }).fill(bare);
  await page.getByLabel("Type").selectOption("bar");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByText("Still to add: metal content, cost, photos, value.")).toBeVisible();

  await page.goto(`/?q=${tag}`);
  await expect(page.locator(".flip-card")).toHaveCount(2);
  await page.getByLabel("Needs attention").selectOption("metal");
  await expect(page.locator(".flip-card")).toHaveCount(1);
  await expect(page.locator(".flip-card", { hasText: bare }).locator(".flip-gaps")).toContainText("No metal content");
  await page.getByLabel("Needs attention").selectOption("");
  await page.getByLabel("Sort").selectOption("cost");
  await expect(page.locator(".flip-card").first()).toContainText(eagle); // the one with a cost comes first

  // select both and tag them, then mark them seen
  await page.getByRole("button", { name: "Select", exact: true }).click();
  await page.getByRole("button", { name: "Select all on this page" }).click();
  await expect(page.locator(".bulk-count")).toContainText("2 selected");
  await page.getByLabel("Tag for selected").fill(`t-${tag}`);
  await page.getByRole("button", { name: "Add tag" }).click();
  await expect(page.getByText("2 items tagged.")).toBeVisible();
  await page.getByRole("button", { name: "Seen today" }).click();
  await expect(page.getByText("2 items marked as seen today.")).toBeVisible();
  await page.getByRole("button", { name: "Done selecting" }).click();

  // duplicate the eagle: details and metal come along, the price doesn't
  await page.locator(".flip-card", { hasText: eagle }).click();
  await expect(page.getByText("Seen again today")).toBeVisible();
  await page.getByRole("button", { name: "Duplicate" }).click();
  await expect(page.getByText(`Copied from “${eagle}”`)).toBeVisible();
  await expect(page.getByLabel("Product")).toHaveValue("American Silver Eagle");
  await expect(page.getByLabel("Price paid (total for all pieces)")).toHaveValue("");
  await expect(page.getByLabel("Tags")).toHaveValue(`t-${tag}`);
  const copy = `2024 American Silver Eagle ${tag}`;
  await page.getByLabel("Title", { exact: true }).fill(copy);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: copy })).toBeVisible();
  await expect(page.getByText("1 ozt").first()).toBeVisible();
});

test("a checklist counts coins in a set, and a missing one goes on the want list and comes back as found", async ({ page }, info) => {
  // the two projects share one database, so each hunts for a different coin
  const phone = info.project.name === "phone";
  const coin = phone ? "1928-S Peace dollar" : "1928 Peace dollar";
  await signIn(page);
  await addItem(page, "2009 DC and US Territories Quarters Silver Proof Set");
  await expect(page.getByRole("cell", { name: "2009-S Guam quarter" })).toBeVisible();
  await page.getByRole("link", { name: "Tools" }).first().click();
  await page.getByRole("link", { name: /Series checklists/ }).click();
  const card = page.locator(".checklist-card", { hasText: "DC and U.S. Territories Quarters" });
  await expect(card).toContainText("6 of 6");
  await page.locator(".checklist-card", { hasText: "Peace Dollars" }).click();
  await expect(page.getByRole("heading", { name: "Peace Dollars by date and mint" })).toBeVisible();
  const row = page.locator(".checklist-entries li").filter({ has: page.getByText(coin, { exact: true }) });
  await row.getByRole("button", { name: "Add to want list" }).click();
  await expect(row.getByText("on your want list")).toBeVisible();

  await page.goto("/wants");
  const want = page.locator(".want-list li").filter({ has: page.getByText(coin, { exact: true }) }).first();
  await want.getByRole("button", { name: "Got it: add the item" }).click();
  await expect(page.getByText("From your want list.")).toBeVisible();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(coin);
  await page.getByLabel("Year").fill("1928");
  if (phone) await page.getByLabel("Mint mark").fill("S");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: coin })).toBeVisible();
  await page.goto("/wants");
  await expect(page.getByRole("heading", { name: "Found" })).toBeVisible();
  await page.goto("/checklists?list=peace-dollars");
  await expect(page.locator(".checklist-entries li.have").filter({ has: page.getByText(coin, { exact: true }) })).toBeVisible();
});

test("sales report, price alerts, inventory check and labels", async ({ page }) => {
  const title = unique("Sold Morgan");
  await signIn(page);
  await addItem(page, title, async (p) => {
    await p.getByLabel("Price paid (total for all pieces)").fill("60");
    await p.getByLabel("Acquired").fill("2024-01-10");
    await p.getByLabel("Status").selectOption("sold");
    await p.getByLabel("Sale date").fill("2026-03-01");
    await p.getByLabel("Sale price").fill("100");
    await p.getByLabel("Selling fees").fill("10");
  });
  await page.goto("/sales");
  const row = page.locator("table.figures tbody tr", { hasText: title });
  await expect(row).toContainText("$90.00");
  await expect(row).toContainText("+$30.00");
  await expect(row).toContainText("over a year");
  await expect(page.locator(".sales-years tbody tr", { hasText: "2026" })).toBeVisible();

  await page.goto("/alerts");
  await page.getByLabel("Price per ounce").fill("12.34");
  await page.getByLabel("Note").fill("buy more");
  await page.getByRole("button", { name: "Add alert" }).click();
  const alert = page.locator(".plain-list li", { hasText: "$12.34" }).first();
  await expect(alert).toContainText("Silver at or below $12.34");
  await expect(alert).toContainText("Waiting");
  await alert.getByRole("button", { name: "Remove" }).click();

  // a location, something in it, a check and a label
  const box = unique("Box");
  await page.goto("/settings");
  await page.getByLabel("New location name").fill(box);
  await page.getByRole("button", { name: "Add location" }).click();
  await expect(page.locator(".plain-list li", { hasText: box })).toBeVisible();
  const coin = unique("Stored coin");
  await addItem(page, coin, async (p) => { await p.getByLabel("Storage location").selectOption({ label: box }); });
  await page.goto("/inventory-check");
  await page.getByLabel("Location").selectOption({ label: `${box} (1)` });
  await expect(page.getByText("0 of 1 seen today")).toBeVisible();
  await page.locator(".check-list li", { hasText: coin }).getByRole("checkbox").check();
  await expect(page.getByText("1 of 1 seen today. All accounted for.")).toBeVisible();

  await page.goto("/labels");
  const label = page.locator(".label", { hasText: box });
  await expect(label).toBeVisible();
  const ok = await label.locator("img").evaluate((img: HTMLImageElement) => img.decode().then(() => img.naturalWidth > 0));
  expect(ok).toBe(true);
});

test("import a spreadsheet: preview first, then save", async ({ page }) => {
  const tag = unique("imp").replace(/\s/g, "");
  const csv = `Title,Qty,Price,Location\n2022 American Silver Eagle ${tag},2,70,Import box ${tag}\n,1,,\n10 oz Silver Bar ${tag},1,,\n`;
  await signIn(page);
  await page.goto("/import");
  await page.getByLabel("CSV file").setInputFiles({ name: "coins.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("Nothing is saved yet. 2 rows are ready, 1 can't be read and will be skipped.")).toBeVisible();
  await expect(page.locator(".import-rows tr.bad")).toContainText("Skipped: no title");
  await expect(page.locator(".import-rows tbody tr").first()).toContainText("American Silver Eagle, 1 oz");
  await page.getByRole("button", { name: "Import 2 items" }).click();
  await expect(page.getByText("2 items added.")).toBeVisible();
  await page.goto(`/?q=${tag}`);
  await expect(page.locator(".flip-card")).toHaveCount(2);
  await page.locator(".flip-card", { hasText: "Silver Bar" }).click();
  await expect(page.getByText("9.99 ozt").first()).toBeVisible();
});

test("a read-only login sees the collection and can't change it", async ({ page, browser }) => {
  const name = unique("viewer").replace(/\s/g, "");
  const title = unique("Shown to family");
  await signIn(page);
  await addItem(page, title);
  await page.goto("/settings");
  await page.getByLabel("Username for the read-only login").fill(name);
  await page.getByLabel("Password for the read-only login").fill("family-password-1");
  await page.getByRole("button", { name: "Add read-only login" }).click();
  await expect(page.locator("#viewers .plain-list li", { hasText: name })).toBeVisible();

  const other = await browser.newContext();
  const v = await other.newPage();
  await v.goto(page.url().replace(/\/settings.*/, "/"));
  await v.getByLabel("Username").fill(name);
  await v.getByLabel("Password").fill("family-password-1");
  await v.getByRole("button", { name: "Sign in" }).click();
  await expect(v.getByText("Read-only login: you can look at everything and change nothing.")).toBeVisible();
  await expect(v.getByRole("link", { name: "Add item" })).toHaveCount(0);
  await expect(v.getByRole("link", { name: "Upload photos" })).toHaveCount(0);
  await v.getByLabel("Search").fill(title);
  await v.locator(".flip-card", { hasText: title }).click();
  await expect(v.getByRole("heading", { name: title })).toBeVisible();
  await expect(v.getByRole("button", { name: "Edit details" })).toHaveCount(0);
  await expect(v.getByRole("button", { name: "Delete" })).toHaveCount(0);
  const status = await v.evaluate(async () => (await fetch("/api/v1/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_type: "coin", title: "x" }) })).status);
  expect(status).toBe(403);
  await other.close();
});
