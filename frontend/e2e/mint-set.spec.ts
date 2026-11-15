import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

test("a proof set's coins are broken out, counted for silver, and found by search", async ({ page }) => {
  const title = "2008 United States 50 State Quarters Silver Proof Set";
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.locator("#qs-text").fill(title);
  await expect(page.getByText("5 coins, 0.9042 ozt silver")).toBeVisible();
  await page.getByRole("button", { name: "Fill in the form" }).click();

  await expect(page.getByLabel("Type")).toHaveValue("set");
  await expect(page.getByLabel("Set name")).toHaveValue("50 State Quarters Silver Proof Set");
  await expect(page.locator(".coin-row")).toHaveCount(5);
  await expect(page.locator(".coin-row").first().getByLabel("Coin")).toHaveValue("2008-S Oklahoma quarter");
  await expect(page.getByText("5 coins, 0.9042 ozt silver per set")).toBeVisible();
  await expect(page.getByText("Added up from the coins above")).toBeVisible();
  await page.getByRole("button", { name: "Save item" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("cell", { name: "2008-S Hawaii quarter" })).toBeVisible();
  await expect(page.getByText("Mint set (proof or uncirculated)")).toBeVisible();
  await expect(page.getByText("0.9042 ozt").first()).toBeVisible();

  // searching for one of the coins finds the set
  await page.getByRole("link", { name: "Collection" }).first().click();
  await page.getByLabel("Search").fill("Oklahoma");
  const card = page.locator(".flip-card", { hasText: title }).first(); // each project adds its own
  await expect(card).toBeVisible();
  await expect(card.getByText("Contains 2008-S Oklahoma quarter")).toBeVisible();
  await page.getByLabel("Type").selectOption("set");
  await expect(card).toBeVisible();
});
