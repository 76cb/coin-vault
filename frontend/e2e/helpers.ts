import { expect, Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const fixture = (name: string) => path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", name);

export async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Username").fill(process.env.E2E_USER ?? "admin");
  await page.getByLabel("Password").fill(process.env.E2E_PASSWORD ?? "e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Collection" })).toBeVisible();
}

export const unique = (prefix: string) => `${prefix} ${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
