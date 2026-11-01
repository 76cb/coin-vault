import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { fixture, signIn, unique } from "./helpers";

// copies of the fixtures under names (and contents) of their own, so other tests' uploads never get in the way
const own = (name: string, as: string) => ({
  name: as, mimeType: "image/jpeg", buffer: Buffer.concat([readFileSync(fixture(name)), Buffer.from(` ${as}`)]),
});

test("bulk upload pairs photos, creates one item and adds the other pair to it", async ({ page }) => {
  const title = unique("1921 Morgan");
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();

  const tag = unique("pair").replace(/\s/g, "_");
  await page
    .locator(".dropzone input[type=file]")
    .setInputFiles([
      own("IMG_2002.jpg", `IMG_${tag}_2.jpg`), own("0007_rev.jpg", `${tag}_rev.jpg`),
      own("IMG_2001.jpg", `IMG_${tag}_1.jpg`), own("0007_obv.jpg", `${tag}_obv.jpg`),
    ]);

  const mine = page.locator(".group-card").filter({ hasText: tag });
  const byName = mine.filter({ hasText: "Paired by file name" });
  const byOrder = mine.filter({ hasText: "Paired by upload order" });
  await expect(byName).toBeVisible({ timeout: 30_000 }); // four photos are checked and resized on upload: slow on a busy CI runner
  await expect(byOrder).toBeVisible();
  await expect(byName.getByRole("combobox", { name: new RegExp(`${tag}_obv`) })).toHaveValue("obverse");
  await expect(byName.getByRole("combobox", { name: new RegExp(`${tag}_rev`) })).toHaveValue("reverse");
  await expect(byOrder.getByRole("combobox", { name: new RegExp(`IMG_${tag}_1`) })).toHaveValue("obverse");

  // Save the named pair as a new item.
  await byName.getByLabel("Title", { exact: true }).fill(title);
  await byName.getByRole("button", { name: "Create item" }).click();
  await expect(page.locator(".success").getByRole("link", { name: title })).toBeVisible();

  // Add the other pair to the item just created.
  await byOrder.getByRole("radio", { name: "Add to existing" }).click();
  await byOrder.getByLabel("Find an item").fill(title);
  await byOrder.getByRole("button", { name: new RegExp(title) }).click();
  await expect(mine).toHaveCount(0);

  await page.locator(".success").getByRole("link", { name: title }).first().click();
  await expect(page.locator(".photo-list li")).toHaveCount(4);
});

test("split a pair and discard one photo", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  const tag = unique("split").replace(/\s/g, "_");
  const [a, b] = [`IMG_${tag}_a.jpg`, `IMG_${tag}_b.jpg`];
  await page.locator(".dropzone input[type=file]").setInputFiles([own("IMG_2001.jpg", a), own("IMG_2002.jpg", b)]);
  const mine = page.locator(".group-card").filter({ hasText: tag });
  await expect(mine).toHaveCount(1, { timeout: 30_000 }); // photos are checked and resized on upload: slow on a busy CI runner
  await expect(mine.locator("figure")).toHaveCount(2);
  await mine.getByRole("button", { name: "Split" }).click();
  await expect(mine).toHaveCount(2);
  await page.locator(".group-card", { hasText: a }).getByRole("button", { name: "Discard" }).click();
  await expect(mine).toHaveCount(1);
  await page.locator(".group-card", { hasText: b }).getByRole("button", { name: "Discard" }).click();
  await expect(mine).toHaveCount(0);
});

test("a non-image file is reported, not uploaded", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  await page.locator(".dropzone input[type=file]").setInputFiles({ name: "notes.jpg", mimeType: "image/jpeg", buffer: Buffer.from("not really a jpeg") });
  await expect(page.getByText("notes.jpg")).toBeVisible();
  await expect(page.getByText(/Not a supported image/)).toBeVisible();
});
