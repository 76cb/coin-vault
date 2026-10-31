import { expect, test } from "@playwright/test";

import { fixture, signIn, unique } from "./helpers";

test("put a photo from one item on another, from the item page and the Photos page", async ({ page }) => {
  await signIn(page);
  const make = async (title: string) => {
    await page.goto("/items/new");
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page.getByRole("button", { name: "Save item" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    return page.url();
  };
  const first = unique("Library source");
  await make(first);
  await page.locator(".photo-manager input[type=file]").setInputFiles([fixture("IMG_2001.jpg")]);
  await expect(page.locator(".photo-list li")).toHaveCount(1);

  const second = unique("Library target");
  await make(second);
  await page.getByRole("button", { name: "Choose from your photos" }).click();
  await page.locator(".library-tile", { hasText: first }).first().click();
  await expect(page.getByLabel("Make it the cover photo")).toBeChecked(); // no photos yet: it becomes the cover
  await page.getByRole("button", { name: "Add this photo" }).click();
  await expect(page.locator(".photo-list li")).toHaveCount(1);
  await expect(page.locator(".photo-list li.is-cover")).toHaveCount(1);

  await page.getByRole("link", { name: "Photos", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Photos" })).toBeVisible();
  await page.locator(".library-tile", { hasText: first }).first().click();
  const detail = page.getByRole("complementary", { name: "Selected photo" });
  await expect(detail.getByRole("link", { name: first })).toBeVisible();
  await expect(detail.getByRole("link", { name: second })).toBeVisible();
});
