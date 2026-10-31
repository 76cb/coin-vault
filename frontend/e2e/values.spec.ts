import { expect, test } from "@playwright/test";

import { signIn, unique } from "./helpers";

// The e2e server runs without price polling and without network access to providers,
// so these tests cover what works with no spot prices: reference compositions, the
// dashboard's empty state, and saving a provider key.

test("reference composition fills the metal content", async ({ page }) => {
  const title = unique("1964 Washington quarter");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Country").fill("United States");
  await page.getByLabel("Denomination").fill("Quarter");
  await page.getByLabel("Year").fill("1964");
  await page.getByLabel("Quantity").fill("4");

  const suggestion = page.locator(".suggest");
  await expect(suggestion).toContainText("Looks like:");
  await expect(suggestion).toContainText("US quarter, 90% silver");
  await suggestion.getByRole("button", { name: "Use these figures" }).click();
  await expect(page.getByText("0.1808 ozt pure, from the reference")).toBeVisible();
  await expect(suggestion).toHaveCount(0);
  await page.getByRole("button", { name: "Save item" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("0.1808 ozt (reference)")).toBeVisible();
  // No spot price in the test server: the panel says so instead of showing a made-up value.
  await expect(page.getByText("No spot price yet for Silver")).toBeVisible();
});

test("ambiguous details offer every match", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Country").fill("United States");
  await page.getByLabel("Denomination").fill("Dollar");
  await page.getByLabel("Year").fill("1881");
  const suggestion = page.locator(".suggest");
  await expect(suggestion).toContainText("could be any of these");
  await expect(suggestion.getByRole("listitem")).toHaveCount(2);
  await page.getByLabel("Title").fill("1881 Morgan");
  await expect(suggestion).toContainText("Looks like:");
  await expect(suggestion.getByRole("listitem")).toHaveCount(1);
});

test("dashboard shows totals without spot prices", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Collection value")).toBeVisible();
  await expect(page.getByText("No spot prices have been fetched yet")).toBeVisible();
  await expect(page.getByRole("heading", { name: "By type" })).toBeVisible();
});

test("provider key is saved and never shown back", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Settings" }).click();
  const card = page.locator("article.provider", { has: page.getByRole("heading", { name: /SoldComps/ }) });
  await expect(card).toBeVisible();
  const field = card.getByLabel(/API key/);
  if (await field.count() === 0) {
    // left over from an earlier run on a reused server
    page.once("dialog", (d) => d.accept());
    await card.getByRole("button", { name: "Remove" }).click();
  }
  await card.getByLabel(/API key/).fill("sc_e2e_secret_7f3a");
  await card.getByRole("button", { name: "Save key" }).click();
  await expect(card.getByText("Key saved, ending")).toBeVisible();
  await expect(card.locator("code")).toHaveText("7f3a");
  await expect(page.locator("body")).not.toContainText("sc_e2e_secret");
  await expect(card.getByText(/requests this period/)).toBeVisible();

  const capField = card.getByLabel(/Stop after/);
  const cap = (await capField.inputValue()) === "50" ? "60" : "50"; // the server is shared with the other project
  await capField.fill(cap);
  await card.getByRole("button", { name: "Set" }).click();
  await expect(card.getByText(new RegExp(`of ${cap} requests this period`))).toBeVisible();

  await page.reload();
  await expect(page.locator("body")).not.toContainText("sc_e2e_secret");
  await expect(card.locator("code")).toHaveText("7f3a");
});


test("enter a market value by hand", async ({ page }) => {
  const title = unique("1921 Peace Dollar");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Quantity").fill("2");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("No market value yet")).toBeVisible();

  await page.getByRole("tab", { name: "Enter a value" }).click();
  await page.getByLabel("Value of one piece").fill("55");
  await expect(page.getByText("For all 2: $110.00")).toBeVisible();
  await page.getByLabel("Source").fill("Dealer quote");
  await page.getByRole("button", { name: "Save market value" }).click();

  const panel = page.locator(".value-panel");
  await expect(panel.getByText("$110.00").first()).toBeVisible();
  await expect(panel.getByText("$55.00 each")).toBeVisible();
  await expect(page.locator(".ledger")).toContainText("Dealer quote");
  // SoldComps search needs a key; without one it says where to add it
  await page.getByRole("tab", { name: "Search sold listings" }).click();
  const prov = page.locator(".market-panel");
  await expect(prov).toContainText(/SoldComps|Search eBay sold listings/);
});
