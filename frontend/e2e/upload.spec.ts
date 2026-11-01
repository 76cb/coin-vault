import { expect, test } from "@playwright/test";

import { fixture, signIn, unique } from "./helpers";

test("bulk upload pairs photos, creates one item and adds the other pair to it", async ({ page }) => {
  const title = unique("1921 Morgan");
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();

  await page
    .locator(".dropzone input[type=file]")
    .setInputFiles([fixture("IMG_2002.jpg"), fixture("0007_rev.jpg"), fixture("IMG_2001.jpg"), fixture("0007_obv.jpg")]);

  const byName = page.locator(".group-card", { hasText: "Paired by file name" }).first();
  const byOrder = page.locator(".group-card", { hasText: "Paired by upload order" }).first();
  await expect(byName).toBeVisible({ timeout: 30_000 }); // four photos are checked and resized on upload: slow on a busy CI runner
  await expect(byOrder).toBeVisible();
  await expect(byName.getByRole("combobox", { name: /0007_obv/ })).toHaveValue("obverse");
  await expect(byName.getByRole("combobox", { name: /0007_rev/ })).toHaveValue("reverse");
  await expect(byOrder.getByRole("combobox", { name: /IMG_2001/ })).toHaveValue("obverse");

  // Save the named pair as a new item.
  await byName.getByLabel("Title", { exact: true }).fill(title);
  await byName.getByRole("button", { name: "Create item" }).click();
  await expect(page.locator(".success").getByRole("link", { name: title })).toBeVisible();

  // Add the other pair to the item just created.
  await byOrder.getByRole("radio", { name: "Add to existing" }).click();
  await byOrder.getByLabel("Find an item").fill(title);
  await byOrder.getByRole("button", { name: new RegExp(title) }).click();
  await expect(page.locator(".group-card")).toHaveCount(0);

  await page.locator(".success").getByRole("link", { name: title }).first().click();
  await expect(page.locator(".photo-list li")).toHaveCount(4);
});

test("split a pair and discard one photo", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  await page.locator(".dropzone input[type=file]").setInputFiles([fixture("IMG_2001.jpg"), fixture("IMG_2002.jpg")]);
  const card = page.locator(".group-card").first();
  await expect(card.locator("figure")).toHaveCount(2, { timeout: 30_000 });
  await card.getByRole("button", { name: "Split" }).click();
  await expect(page.locator(".group-card")).toHaveCount(2);
  await page.locator(".group-card").first().getByRole("button", { name: "Discard" }).click();
  await expect(page.locator(".group-card")).toHaveCount(1);
  await page.locator(".group-card").first().getByRole("button", { name: "Discard" }).click();
  await expect(page.getByText("Nothing waiting")).toBeVisible();
});

test("a non-image file is reported, not uploaded", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  await page.locator(".dropzone input[type=file]").setInputFiles({ name: "notes.jpg", mimeType: "image/jpeg", buffer: Buffer.from("not really a jpeg") });
  await expect(page.getByText("notes.jpg")).toBeVisible();
  await expect(page.getByText(/Not a supported image/)).toBeVisible();
});
