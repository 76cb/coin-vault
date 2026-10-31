import { expect, test } from "@playwright/test";

import { fixture, signIn, unique } from "./helpers";

test("crop, turn and brighten a photo, then reset it", async ({ page }) => {
  const title = unique("Photo editor");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.locator(".photo-manager input[type=file]").setInputFiles([fixture("0007_obv.jpg")]);
  const row = page.locator(".photo-list li").first();
  await expect(row).toContainText("1300×1300");

  await row.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.getByRole("dialog");
  await expect(editor.locator(".pe-box")).toBeVisible();
  await expect(editor.getByRole("button", { name: "Save photo" })).toBeDisabled(); // nothing changed yet

  // drag the bottom-right corner in by a quarter of the width and a tenth of the height
  const box = (await editor.locator(".pe-canvas").boundingBox())!;
  const handle = editor.locator(".pe-se");
  const h = (await handle.boundingBox())!;
  await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2);
  await page.mouse.down();
  await page.mouse.move(h.x + h.width / 2 - box.width / 4, h.y + h.height / 2 - box.height / 10, { steps: 5 });
  await page.mouse.up();
  await editor.getByRole("button", { name: "Turn right" }).click(); // starts the crop again: free shape, whole frame
  await editor.getByRole("button", { name: "4:3" }).click();
  await editor.getByRole("tab", { name: "Adjust" }).click();
  await editor.getByLabel("Brightness", { exact: true }).fill("25");
  await editor.getByRole("button", { name: "Save photo" }).click();
  await expect(editor).toBeHidden();

  // 4:3 of the 1300 x 1300 frame: 1300 wide, 975 high
  await expect(row).toContainText(/1300×97\d, edited/);

  await row.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor.locator(".pe-box")).toBeVisible();
  await editor.getByRole("button", { name: "Reset to original" }).click();
  await editor.getByRole("button", { name: "Save photo" }).click();
  await expect(editor).toBeHidden();
  await expect(row).toContainText("1300×1300");
  await expect(row).not.toContainText("edited");
});

test("cut a coin out as a circle", async ({ page }) => {
  const title = unique("Circle cut");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.locator(".photo-manager input[type=file]").setInputFiles([fixture("0007_rev.jpg")]);
  const row = page.locator(".photo-list li").first();
  await expect(row).toContainText("1300×1300");

  await row.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.getByRole("dialog");
  await editor.getByRole("button", { name: "Find the coin" }).click();
  await expect(editor.getByText("Found it.")).toBeVisible();
  await expect(editor.getByRole("button", { name: "Circle" })).toHaveAttribute("aria-pressed", "true");
  await expect(editor.locator(".pe-cut-shade")).toBeVisible();
  await editor.getByRole("button", { name: "White" }).click();
  await editor.getByRole("button", { name: "Save photo" }).click();
  await expect(editor).toBeHidden();
  // the test coin's rim is 80% of the photo across
  await expect(row).toContainText(/10[34]\d×10[34]\d, edited/);

  await row.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor.getByRole("button", { name: "Circle" })).toHaveAttribute("aria-pressed", "true"); // remembered
  await expect(editor.getByRole("button", { name: "White" })).toHaveAttribute("aria-pressed", "true");
  await editor.getByRole("button", { name: "Cancel" }).click();
});
