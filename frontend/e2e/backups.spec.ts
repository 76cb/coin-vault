import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

test("back up now, see it listed, and download it", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Settings" }).click();
  const section = page.getByRole("region", { name: "Backups" });
  await section.getByRole("button", { name: "Back up now" }).click();
  await expect(section.getByText("Backup made and checked.")).toBeVisible();
  await expect(section.getByRole("status")).toContainText("Last backup");
  await expect(section.locator(".backup-list tbody tr").first()).toContainText("made by hand");

  const download = page.waitForEvent("download");
  await section.getByRole("link", { name: /Download the latest/ }).click();
  expect((await download).suggestedFilename()).toMatch(/^coinvault-backup-.*\.tar$/);

  // the schedule
  const at = section.getByLabel("At");
  await at.fill((await at.inputValue()) === "02:45" ? "04:05" : "02:45"); // the desktop and phone runs share a server
  await section.getByRole("button", { name: "Save schedule" }).click();
  await expect(section.getByText("Schedule saved.")).toBeVisible();
});

test("value updates: schedule and explanation in Settings", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Settings" }).click();
  const s = page.getByRole("region", { name: "Value updates" });
  await expect(s.getByText("Once a week, the PCGS price guide values")).toBeVisible();
  await expect(s.getByText(/No items to follow yet|Following/)).toBeVisible();
  await s.getByRole("combobox", { name: "On" }).selectOption("sat");
  await s.getByRole("button", { name: "Save schedule" }).click();
  await expect(s.getByText("Schedule saved.")).toBeVisible();
  await expect(s.getByText(/next Sat/)).toHaveCount(0); // the e2e server runs no scheduler, so there's no next run to show
  await s.getByRole("combobox", { name: "On" }).selectOption("sun");
  await s.getByRole("button", { name: "Save schedule" }).click();
});
