import { readFileSync } from "node:fs";

import { expect, Page, test } from "@playwright/test";

import { fixture, signIn, unique } from "./helpers";

// The AI server (Ollama) isn't running in tests: its answers are faked at Coin Vault's own API, like PCGS and Numista.

const described = (title: string, extra: Record<string, unknown> = {}) => ({
  item_type: "coin", title, quantity: 1, metal: null,
  details: { country: "United States", year: 1956, mint_mark: "D", series: "Washington", denomination: "25c" },
  condition: null, recognized: ["United States 25c", "Washington", "1956"], notes: [], compositions: [],
  ...extra,
});

function identified(title: string, same: { id: number; title: string }[] = [], extra: Record<string, unknown> = {}) {
  return {
    model: "gemma4:26b", seconds: 3.4, load_seconds: 0, confidence: "high", title, kind: "coin", country: "United States",
    denomination: "Quarter Dollar", year: 1956, mint_mark: "D", series: "Washington Quarter", weight_text: null, holder: null,
    barcodes: [], notes: "The mint mark is small but clear.", described: described(title), same_photos: [],
    same_coin: same.map((s) => ({ ...s, thumb: null, quantity: 1, why: "1956 D Washington" })),
    ...extra,
  };
}

async function aiOn(page: Page) {
  await page.route("**/api/v1/ai", (route) => route.fulfill({ json: { ready: true, model: "gemma4:26b" } }));
}

const own = (name: string, tag: string) => ({
  name, mimeType: "image/jpeg", buffer: Buffer.concat([readFileSync(fixture(name)), Buffer.from(` ${tag} ${name}`)]),
});

test("an admin connects the AI server in Settings", async ({ page }) => {
  let saved = { url: "", model: null as string | null, ready: false };
  await page.route("**/api/v1/ai/settings", async (route) => {
    if (route.request().method() === "PUT") {
      const b = route.request().postDataJSON();
      saved = { url: b.url, model: b.model || null, ready: Boolean(b.url) };
    }
    return route.fulfill({ json: saved });
  });
  await page.route("**/api/v1/ai/check", (route) => route.fulfill({
    json: {
      url: "http://192.168.1.80:11434", version: "0.13.0",
      models: [
        { name: "gemma4:26b", size: 17_000_000_000, parameter_size: "26B", quantization: "Q4_K_M", vision: true },
        { name: "llama3:8b", size: 4_700_000_000, parameter_size: "8.0B", quantization: "Q4_0", vision: false },
      ],
    },
  }));
  await signIn(page);
  await page.goto("/settings");
  const panel = page.locator(".ai-settings");
  await expect(panel).toContainText("Off: no AI server set up.");
  await panel.getByLabel("Ollama address").fill("http://192.168.1.80:11434/");
  await panel.getByRole("button", { name: "Check the server" }).click();
  await expect(panel).toContainText("Ollama 0.13.0 is answering.");
  await expect(panel.getByRole("radio", { name: /gemma4:26b/ })).toBeChecked();
  await expect(panel).toContainText("Can't see photos, so not offered: llama3:8b.");
  await panel.getByRole("button", { name: "Use this model" }).click();
  await expect(panel).toContainText("On: gemma4:26b at 192.168.1.80:11434");
  await expect(panel.locator(".success")).toContainText("Saved.");
});

test("identify an item from its photos, fill the blanks, and suggest a grade", async ({ page }) => {
  await aiOn(page);
  const title = unique("Quarter for AI");
  await signIn(page);
  await page.goto("/items/new");
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.locator(".photo-manager input[type=file]").setInputFiles([own("0007_obv.jpg", title), own("0007_rev.jpg", title)]);
  await expect(page.locator(".photo-list li")).toHaveCount(2);

  let asked: { photos: { sha256: string; role: string }[]; item_id: number } | null = null;
  await page.route("**/api/v1/ai/identify", async (route) => {
    asked = route.request().postDataJSON();
    await new Promise((r) => setTimeout(r, 300));
    return route.fulfill({ json: identified("1956 D Washington Quarter", [{ id: 999999, title: "1956-D Quarter, roll find" }]) });
  });
  await page.route("**/api/v1/ai/grade", (route) => route.fulfill({
    json: {
      model: "gemma4:26b", seconds: 5.1, low: "VF20", high: "VF30", low_number: 20, high_number: 30,
      summary: "Moderate, even wear.", wear: "Hair above the ear is worn flat.", surfaces: "Grey toning.", marks: [], problems: [],
      photo_advice: "An angled shot would show any luster left.",
    },
  }));

  const section = page.getByRole("region", { name: "From the photos" });
  await section.getByRole("button", { name: "Identify from the photos" }).click();
  await expect(section.getByRole("status").first()).toContainText("Looking at the photos");
  await expect(section.locator(".ai-verdict")).toContainText("1956 D Washington Quarter");
  await expect(section.locator(".ai-conf")).toHaveText("Clear read");
  await expect(section.getByRole("link", { name: "1956-D Quarter, roll find" })).toBeVisible();
  expect(asked!.photos.map((p) => p.role)).toEqual(["obverse", "reverse"]);
  expect(asked!.photos[0].sha256).toMatch(/^[0-9a-f]{64}$/);

  await section.getByRole("button", { name: "Edit with these details" }).click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(title); // the title stays
  await expect(page.getByLabel("Mint mark")).toHaveValue("D");
  await expect(page.getByLabel("Year")).toHaveValue("1956");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.locator(".item-facts")).toContainText("1956");

  await section.getByRole("button", { name: "Suggest a grade" }).click();
  await expect(section.locator(".ai-range")).toHaveText("VF20 to VF30");
  await expect(section.locator(".ai-caution")).toContainText("not a grade");
  await expect(section.locator(".ai-grade-notes")).toContainText("None seen");
  await section.getByRole("button", { name: "Add to the item's notes" }).click();
  await expect(section.getByText("Added to the item's notes.")).toBeVisible();
  await expect(page.locator(".notes")).toContainText("Grade suggestion from photos (gemma4:26b");
  await expect(page.locator(".notes")).toContainText("VF20 to VF30");
});

test("AI on a bulk upload: use its title, or fill in every detail on Add item", async ({ page }) => {
  await aiOn(page);
  const tag = unique("ai-upload").replace(/\s/g, "_");
  await page.route("**/api/v1/ai/identify", (route) => route.fulfill({
    json: identified("2015 S Bombay Hook Quarter PCGS PR70 DCAM", [], {
      holder: { service: "PCGS", grade: "PR70 DCAM", cert_number: "3257-3628", pcgs_number: "382795", label_text: null },
      described: described("2015 S Bombay Hook Quarter PCGS PR70 DCAM", {
        details: { country: "United States", year: 2015, mint_mark: "S", denomination: "25c", pcgs_number: "382795" },
        condition: { grading: "slabbed", grading_service: "PCGS", grade_text: "PR70", sheldon_grade: 70, designations: ["DCAM"], details_reason: null, cert_number: "3257-3628" },
      }),
    }),
  }));
  await signIn(page);
  await page.getByRole("link", { name: "Upload photos" }).first().click();
  await page.locator(".dropzone input[type=file]").setInputFiles([own("0007_obv.jpg", tag), own("0007_rev.jpg", tag)].map((f, i) => ({ ...f, name: `${tag}_${i ? "rev" : "obv"}.jpg` })));
  const card = page.locator(".group-card", { hasText: `${tag}_obv.jpg` });
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: "Identify from the photos" }).click();
  await expect(card.locator(".ai-holder")).toContainText("In a PCGS holder, graded PR70 DCAM, cert 3257-3628, PCGS #382795.");
  await card.getByRole("button", { name: "Use this title" }).click();
  await expect(card.getByLabel("Title", { exact: true })).toHaveValue("2015 S Bombay Hook Quarter PCGS PR70 DCAM");

  await card.getByRole("button", { name: "Fill in all the details" }).click();
  await expect(page.getByRole("heading", { name: "Add item" })).toBeVisible();
  await expect(page.getByText("Filled in from what the AI read on the photos.")).toBeVisible();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("2015 S Bombay Hook Quarter PCGS PR70 DCAM");
  await expect(page.getByLabel("Cert number")).toHaveValue("3257-3628");
  await expect(page.locator(".chosen-list li")).toHaveCount(2);
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: "2015 S Bombay Hook Quarter PCGS PR70 DCAM" })).toBeVisible();
  await expect(page.locator(".photo-list li")).toHaveCount(2);
});
