import { expect, test } from "@playwright/test";

import { fixture, signIn, unique } from "./helpers";

test("add an item by hand, then add photos and set a cover", async ({ page }) => {
  const title = unique("1881-S Morgan Dollar");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();

  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Year").fill("1881");
  await page.getByLabel("Mint mark").fill("S");
  await page.getByRole("button", { name: "Add metal" }).click();
  await page.getByLabel("Gross weight", { exact: true }).fill("26.73");
  await page.getByLabel("Fineness").fill("0.9");
  await expect(page.getByText("≈ 0.7735 ozt pure")).toBeVisible();
  await page.getByRole("radio", { name: "Slabbed" }).click();
  await page.getByLabel("Grading company").fill("PCGS");
  await page.getByLabel("Cert number").fill("40123456");
  await page.getByLabel("Grade as written").fill("MS63");
  await page.getByLabel("Price paid (total for all pieces)").fill("85");
  await page.getByRole("button", { name: "Save item" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("PCGS MS63, cert 40123456")).toBeVisible();
  await expect(page.getByText("0.7735 ozt")).toBeVisible();

  // Two photos into an item with none: they become obverse and reverse.
  await page.locator(".photo-manager input[type=file]").setInputFiles([fixture("0007_obv.jpg"), fixture("0007_rev.jpg")]);
  const rows = page.locator(".photo-list li");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0).getByRole("combobox")).toHaveValue("obverse");
  await expect(rows.nth(1).getByRole("combobox")).toHaveValue("reverse");
  await expect(rows.nth(0).getByText("Cover")).toBeVisible();

  await rows.nth(1).getByRole("button", { name: "Make cover" }).click();
  await expect(rows.nth(1).getByText("Cover")).toBeVisible();
  await rows.nth(1).getByRole("button", { name: "Move earlier" }).click();
  await expect(rows.nth(0).getByRole("combobox")).toHaveValue("reverse");

  // It shows in the collection with its cover photo.
  await page.getByRole("link", { name: "Collection" }).first().click();
  await page.getByLabel("Search").fill(title);
  const card = page.locator(".flip-card", { hasText: title });
  await expect(card).toBeVisible();
  await expect(card.locator("img")).toHaveAttribute("src", /\/thumb$/);
});

test("editing keeps fields and records value changes in history", async ({ page }) => {
  const title = unique("Peace Dollar");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Price paid (total for all pieces)").fill("38");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Price paid (total for all pieces)").fill("42");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("$42.00").first()).toBeVisible();
  await page.getByRole("button", { name: /Show changes/ }).click();
  const change = page.locator(".audit tbody tr", { hasText: "purchase price" }).first(); // newest first
  await expect(change).toContainText("38");
  await expect(change).toContainText("42");
});

test("gross weight in troy ounces, a platinum Lunar by face value, and a cent's composition", async ({ page }) => {
  await signIn(page);
  await page.goto("/items/new");
  // NGC's way of writing it: the reference is the 1/10 oz platinum Lunar, from the $15 face value
  await page.locator("#qs-text").fill("2026P Australia Pt $15 Year of the Horse NGC MS70");
  await expect(page.locator(".qs-metal")).toContainText("Australian Lunar Series III Platinum 1/10 oz");
  await page.locator("#qs-text").fill("2027P Australia G$5 Year of the Goat NGC MS 69");
  await expect(page.locator(".qs-metal")).toContainText("Perth Lunar III gold 1/20 oz");
  await page.locator("#qs-text").fill("2025 D Lincoln Cent");
  await expect(page.locator(".qs-metal")).toContainText("No precious metal: copper-plated zinc");

  // typed by hand, in troy ounces
  const title = unique("Platinum round");
  await page.goto("/items/new");
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Add metal" }).click();
  const row = page.locator(".metal-row").last();
  await row.getByLabel("Metal").selectOption("Pt");
  await row.getByLabel("Gross weight unit").selectOption("ozt");
  await row.getByLabel("Gross weight", { exact: true }).fill("1/10");
  await row.getByLabel("Fineness").fill("0.9995");
  await expect(row.locator(".metal-preview")).toContainText("3.11 g, ≈ 0.1000 ozt pure");
  // switching the unit converts what's typed, so the metal stays the same
  await row.getByLabel("Gross weight unit").selectOption("g");
  await expect(row.getByLabel("Gross weight", { exact: true })).toHaveValue("3.110348");
  await row.getByLabel("Gross weight unit").selectOption("ozt");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.locator("table.figures").first()).toContainText("3.110348 g");
});
