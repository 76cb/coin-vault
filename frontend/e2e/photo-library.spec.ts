import { readFileSync } from "node:fs";

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

test("delete photos from the Photos page", async ({ page }) => {
  await signIn(page);
  const title = unique("Delete photos");
  await page.goto("/items/new");
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  // copies of the fixtures that no other test uploads (bytes after a JPEG's end are ignored, but change its hash)
  const own = (name: string) => ({
    name, mimeType: "image/jpeg", buffer: Buffer.concat([readFileSync(fixture(name)), Buffer.from(` ${title} ${name}`)]),
  });
  await page.locator(".photo-manager input[type=file]").setInputFiles([own("0007_obv.jpg"), own("0007_rev.jpg")]);
  await expect(page.locator(".photo-list li")).toHaveCount(2);
  const itemUrl = page.url();

  await page.getByRole("link", { name: "Photos", exact: true }).click();
  // one photo, from its panel
  page.once("dialog", (d) => { expect(d.message()).toContain(title); d.accept(); });
  await page.locator(".library-tile", { hasText: title }).first().click();
  await page.getByRole("complementary", { name: "Selected photo" }).getByRole("button", { name: "Delete photo" }).click();
  await expect(page.getByText("Deleted 1 photo")).toBeVisible();
  // the other, by selecting several
  await page.getByRole("button", { name: "Select photos" }).click();
  await page.locator(".library-tile", { hasText: title }).first().click();
  await expect(page.getByText("1 selected")).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete 1 photo" }).click();
  await expect(page.getByText("Deleted 1 photo")).toBeVisible();
  await expect(page.locator(".library-tile", { hasText: title })).toHaveCount(0);

  await page.goto(itemUrl);
  await expect(page.locator(".photo-list li")).toHaveCount(0);
});

test("pick uploaded photos on the Photos page and create an item from them", async ({ page }) => {
  await signIn(page);
  const tag = `pick${Date.now().toString(36)}`;
  const title = unique("1964 Washington quarter");
  const own = (from: string, name: string) => ({
    name, mimeType: "image/jpeg", buffer: Buffer.concat([readFileSync(fixture(from)), Buffer.from(` ${tag} ${name}`)]),
  });
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  await page.locator(".dropzone input[type=file]").setInputFiles([own("0007_rev.jpg", `${tag}_rev.jpg`), own("0007_obv.jpg", `${tag}_obv.jpg`)]);
  await expect(page.locator(".group-card", { hasText: `${tag}_obv.jpg` })).toBeVisible();

  await page.getByRole("link", { name: "Photos", exact: true }).click();
  await page.getByRole("radio", { name: "Not on an item" }).click();
  await page.getByRole("button", { name: "Select photos" }).click();
  // picked back first: the sides still come from the file names
  await page.locator(`.library-tile[title="${tag}_rev.jpg"]`).click();
  await page.locator(`.library-tile[title="${tag}_obv.jpg"]`).click();
  await expect(page.getByText("2 selected")).toBeVisible();
  await page.getByRole("button", { name: "Create an item from these 2" }).click();

  await expect(page.getByRole("heading", { name: "2 photos for this item" })).toBeVisible();
  await expect(page.getByLabel("Side of photo 1")).toHaveValue("reverse");
  await expect(page.getByLabel("Side of photo 2")).toHaveValue("obverse");
  await page.getByRole("button", { name: "Move photo 2 earlier" }).click();
  await expect(page.getByLabel("Side of photo 1")).toHaveValue("obverse");
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Save item" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.locator(".photo-list li")).toHaveCount(2);
  await expect(page.locator(".photo-list li.is-cover")).toHaveCount(1);
  // they've left the upload queue, and the Photos page still shows "Not on an item"
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  await expect(page.locator(".group-card", { hasText: `${tag}_obv.jpg` })).toHaveCount(0);
  await page.getByRole("link", { name: "Photos", exact: true }).click();
  await expect(page.getByRole("radio", { name: "Not on an item" })).toHaveAttribute("aria-checked", "true");
  await expect(page.locator(`.library-tile[title="${tag}_obv.jpg"]`)).toHaveCount(0);
});
