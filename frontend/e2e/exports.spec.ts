import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

import { signIn } from "./helpers";

test("export the collection as CSV", async ({ page }) => {
  await signIn(page);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Export CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^coinvault-items-\d{4}-\d{2}-\d{2}\.csv$/);
  const text = await readFile(await download.path(), "utf8");
  expect(text.replace(/^﻿/, "").split("\r\n")[0]).toContain("ID,Title,Kind,Status,Quantity,Description");
});

test("open the insurance report and choose what it shows", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Insurance report" }).click();
  await expect(page.getByRole("heading", { name: "Collection inventory" })).toBeVisible();
  await expect(page.getByText("Total value")).toBeVisible();
  await expect(page.getByRole("button", { name: "Print or save as PDF" })).toBeEnabled();
  const items = page.locator("table.report-items");
  if (await items.count()) {
    await expect(items.getByRole("columnheader", { name: "Paid" })).toHaveCount(0);
    await page.getByLabel("What I paid").check();
    await expect(items.getByRole("columnheader", { name: "Paid" })).toBeVisible();
    await page.getByLabel("Photos").uncheck();
    await expect(items.getByRole("columnheader", { name: "Photo" })).toHaveCount(0);
    await page.getByLabel("Photos").check();
    await page.getByLabel("What I paid").uncheck();
  }
  await page.getByRole("link", { name: "Back to the collection" }).click();
  await expect(page.getByRole("heading", { name: "Collection" })).toBeVisible();
});
