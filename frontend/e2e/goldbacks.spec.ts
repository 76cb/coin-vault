import { expect, test } from "@playwright/test";

import { signIn, unique } from "./helpers";

test("pick Goldbacks by series and denomination, then see the count", async ({ page }) => {
  const series = unique("Test series");
  await signIn(page);
  await page.getByRole("link", { name: "Goldbacks" }).first().click();
  await expect(page.getByRole("heading", { name: "Goldbacks", exact: true })).toBeVisible();

  // a series of its own, so other tests' Goldbacks don't change the counts checked here
  await page.getByRole("radio", { name: /Another/ }).click();
  await page.getByLabel("Series name").fill(series);
  await page.getByRole("button", { name: "One more 5", exact: true }).click();
  await page.getByRole("button", { name: "One more 5", exact: true }).click();
  await page.getByLabel("How many 1/2 Goldback notes").fill("6");
  await page.getByRole("button", { name: "Show the 1/4 and 3 too" }).click();
  await page.getByLabel("How many 3 Goldback notes").fill("1");
  await page.getByLabel("Paid for the 5s, in total").fill("70");
  await expect(page.locator(".gb-save")).toContainText("9 notes, 16 Goldbacks, 0.016 oz gold");
  await page.getByRole("button", { name: "Add 9 notes" }).click();
  await expect(page.getByText(`Added 9 ${series} Goldback notes.`)).toBeVisible();

  const table = page.locator(".gb-table");
  await expect(table.getByRole("row", { name: new RegExp(`${series} 5 2`) })).toBeVisible();
  await expect(table.getByRole("row", { name: new RegExp(`${series} 1/2 6`) })).toBeVisible();
  await expect(table.getByRole("row", { name: new RegExp(`${series} 3 1`) })).toBeVisible();

  // each denomination is an item with its count and its gold
  await page.goto(`/?type=goldback&q=${encodeURIComponent(series)}`);
  await page.getByRole("link", { name: `${series} Goldback 5` }).first().click();
  await expect(page.locator(".item-facts")).toContainText("2 pieces");
  await expect(page.locator("table.figures").first()).toContainText("0.9999");
  await expect(page.locator("table.figures").first()).toContainText("0.005");
});

test("the title reader knows Goldbacks", async ({ page }) => {
  await signIn(page);
  await page.goto("/items/new");
  await page.locator("#qs-text").fill("10 x 1/2 Goldback Nevada 2021");
  await page.getByRole("button", { name: "Fill in the form" }).click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("2021 Nevada Goldback 1/2");
  await expect(page.getByLabel("State or series")).toHaveValue("Nevada");
  await expect(page.getByLabel("Denomination (Goldbacks)")).toHaveValue("0.5");
  await expect(page.getByText("0.0005 troy oz of .9999 gold per note")).toBeVisible();
});
