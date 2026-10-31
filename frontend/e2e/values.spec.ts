import { expect, test } from "@playwright/test";

import { signIn, unique } from "./helpers";

// The e2e server runs without price polling and without network access to providers,
// so these tests cover what works with no spot prices: reference compositions, the
// dashboard's empty state, and saving a provider key.

test("reference composition fills the metal content", async ({ page }) => {
  const title = unique("1964 Washington quarter");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Country").fill("United States");
  await page.getByLabel("Denomination").fill("Quarter");
  await page.getByLabel("Year").fill("1964");
  await page.getByLabel("Quantity").fill("4");

  const suggestion = page.locator(".suggest");
  await expect(suggestion).toContainText("Looks like:");
  await expect(suggestion).toContainText("US quarter, 90% silver");
  await suggestion.getByRole("button", { name: "Use these figures" }).click();
  await expect(page.getByText("0.1808 ozt pure, from the reference")).toBeVisible();
  await expect(suggestion).toHaveCount(0);
  await page.getByRole("button", { name: "Save item" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("0.1808 ozt (reference)")).toBeVisible();
  // No spot price in the test server: the panel says so instead of showing a made-up value.
  await expect(page.getByText("No spot price yet for Silver")).toBeVisible();
});

test("ambiguous details offer every match", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Country").fill("United States");
  await page.getByLabel("Denomination").fill("Dollar");
  await page.getByLabel("Year").fill("1881");
  const suggestion = page.locator(".suggest");
  await expect(suggestion).toContainText("could be any of these");
  await expect(suggestion.getByRole("listitem")).toHaveCount(2);
  await page.getByLabel("Title", { exact: true }).fill("1881 Morgan");
  await expect(suggestion).toContainText("Looks like:");
  await expect(suggestion.getByRole("listitem")).toHaveCount(1);
});

test("dashboard shows totals without spot prices", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Collection value")).toBeVisible();
  await expect(page.getByText("No spot prices have been fetched yet")).toBeVisible();
  await expect(page.getByRole("heading", { name: "By type" })).toBeVisible();
});

test("provider key is saved and never shown back", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Settings" }).click();
  const card = page.locator("article.provider", { has: page.getByRole("heading", { name: /SoldComps/ }) });
  await expect(card).toBeVisible();
  const field = card.getByLabel(/API key/);
  if (await field.count() === 0) {
    // left over from an earlier run on a reused server
    page.once("dialog", (d) => d.accept());
    await card.getByRole("button", { name: "Remove" }).click();
  }
  await card.getByLabel(/API key/).fill("sc_e2e_secret_7f3a");
  await card.getByRole("button", { name: "Save key" }).click();
  await expect(card.getByText("Key saved, ending")).toBeVisible();
  await expect(card.locator("code")).toHaveText("7f3a");
  await expect(page.locator("body")).not.toContainText("sc_e2e_secret");
  await expect(card.getByText(/requests this period/)).toBeVisible();

  const capField = card.getByLabel(/Stop after/);
  const cap = (await capField.inputValue()) === "50" ? "60" : "50"; // the server is shared with the other project
  await capField.fill(cap);
  await card.getByRole("button", { name: "Set" }).click();
  await expect(card.getByText(new RegExp(`of ${cap} requests this period`))).toBeVisible();

  await page.reload();
  await expect(page.locator("body")).not.toContainText("sc_e2e_secret");
  await expect(card.locator("code")).toHaveText("7f3a");
});


test("enter a market value by hand", async ({ page }) => {
  const title = unique("1921 Peace Dollar");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Quantity").fill("2");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("No market value yet")).toBeVisible();

  await page.getByRole("tab", { name: "Enter a value" }).click();
  await page.getByLabel("Value of one piece").fill("55");
  await expect(page.getByText("For all 2: $110.00")).toBeVisible();
  await page.getByLabel("Source").fill("Dealer quote");
  await page.getByRole("button", { name: "Save market value" }).click();

  const panel = page.locator(".value-panel");
  await expect(panel.getByText("$110.00").first()).toBeVisible();
  await expect(panel.getByText("$55.00 each")).toBeVisible();
  await expect(page.locator(".ledger")).toContainText("Dealer quote");
  // SoldComps search needs a key; without one it says where to add it
  await page.getByRole("tab", { name: "Search sold listings" }).click();
  const prov = page.locator(".market-panel");
  await expect(prov).toContainText(/SoldComps|Search eBay sold listings/);
});


test("dark mode switch is remembered", async ({ page }) => {
  await signIn(page);
  const root = page.locator("html");
  const toDark = page.getByRole("button", { name: "Switch to dark mode" });
  if (await toDark.count()) await toDark.click();
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByRole("radio", { name: "Same as device" }).click();
  await expect(root).not.toHaveAttribute("data-theme", /.+/);
});

test("paste a listing title to fill in the form", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  const title = unique("2021 $1 Silver Eagle T2 First Production PCGS MS70 Legends Life");
  await page.locator("#qs-text").fill(title);
  const found = page.locator(".qs-found");
  await expect(found).toContainText("American Silver Eagle");
  await expect(found).toContainText("PCGS MS70, First Production");
  await page.getByRole("button", { name: "Fill in the form" }).click();

  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(title);
  await expect(page.getByLabel("Product")).toHaveValue("American Silver Eagle");
  await expect(page.getByLabel("Grade as written")).toHaveValue("MS70");
  await expect(page.locator(".refpick-chosen")).toContainText("American Silver Eagle, 1 oz");
  await expect(page.locator(".suggest")).toHaveCount(0); // no gold coins offered for a silver eagle
  await page.getByLabel("Price paid (total for all pieces)").fill("53");
  await page.getByRole("button", { name: "Save item" }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("PCGS MS70 First Production")).toBeVisible();
  await expect(page.getByText("1 ozt (reference)")).toBeVisible();
});

test("search the reference list for a bar", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(unique("Heraeus kilo"));
  await page.getByLabel("Type").selectOption("bar");
  await page.getByRole("button", { name: "Add metal" }).click();
  await page.locator(".refpick input").fill("heraeus silver 1 kg");
  await page.getByRole("option", { name: /Heraeus silver bar, 1 kg/ }).click();
  await expect(page.locator(".refpick-chosen")).toContainText("Heraeus silver bar, 1 kg (.9999)");
  await expect(page.getByLabel("Weight", { exact: true })).toHaveValue("1000");
});

test("look up a PCGS cert number", async ({ page }) => {
  // the e2e server can't reach PCGS, so its two endpoints are answered here
  const name = unique("1881-S $1 Morgan");
  await page.route("**/api/v1/pcgs/lookup", (route) =>
    route.fulfill({
      json: {
        coin: {
          cert_no: "12345678", pcgs_no: "7126", name, year: 1881, denomination: "$1", mint_mark: "S", country: "United States",
          grade: "MS65", designation: null, metal_content: "90% Silver, 10% Copper", weight_g: "26.73", price_guide: "325",
          population: 44000, pop_higher: 12000, coinfacts_link: null, series: "Morgan Dollar", images: [],
        },
        item_type: "coin",
        title: `${name} PCGS MS65`,
        details: { country: "United States", year: 1881, mint_mark: "S", series: "Morgan Dollar", denomination: "$1", pcgs_number: "7126" },
        condition: { grading: "slabbed", grading_service: "PCGS", cert_number: "12345678", grade_text: "MS65", sheldon_grade: 65, designations: [], details_reason: null },
        metal: { metal: "Ag", gross_weight_g: "26.73", fineness: "0.9000" },
        currency_note: "PCGS price guide values are in US dollars.",
      },
    }),
  );
  let priceGuideCalls = 0;
  await page.route("**/api/v1/items/*/pcgs/price-guide", (route) => {
    priceGuideCalls += 1;
    return route.fulfill({ status: 201, json: { id: 1, item_id: 1, kind: "manual", value_each: "325", currency: "USD", as_of: "2026-10-31", source: "PCGS Price Guide (MS65)", notes: null, details: null } });
  });

  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.locator("#qs-text").fill("cert #12345678");
  await page.getByRole("button", { name: "Look up cert 12345678 at PCGS" }).click();
  await expect(page.locator(".pcgs-card")).toContainText("PCGS MS65, cert 12345678");
  await expect(page.locator(".pcgs-card")).toContainText("$325");
  await expect(page.getByLabel("Save the PCGS price guide value as its market value")).toBeChecked();
  await page.getByRole("button", { name: "Fill in the form" }).click();

  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(`${name} PCGS MS65`);
  await expect(page.getByLabel("Cert number")).toHaveValue("12345678");
  await expect(page.getByLabel("Gross weight (g)")).toHaveValue("26.73");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: `${name} PCGS MS65` })).toBeVisible();
  expect(priceGuideCalls).toBe(1);
});

test("find a coin on Numista and fill the form from it", async ({ page }) => {
  // the e2e server can't reach Numista, so its answers are given here (in the spec's format, via our API's shape)
  await page.route("**/api/v1/numista/search?*", (route) =>
    route.fulfill({ json: { count: 1, types: [{ id: 420, title: "5 Cents - Victoria", issuer: "Canada", min_year: 1858, max_year: 1901, obverse_thumbnail: null, reverse_thumbnail: null }] } }),
  );
  await page.route("**/api/v1/numista/types/420", (route) =>
    route.fulfill({
      json: {
        id: 420, url: "https://en.numista.com/420", title: "5 Cents - Victoria", issuer: "Canada", min_year: 1858, max_year: 1901,
        denomination: "5 Cents", composition: "Silver (.925) (.925 silver .075 copper)", weight_g: "1.167", size_mm: "15.494",
        references: ["KM# 2"], obverse_thumb: null, reverse_thumb: null,
        issues: [
          { id: 9001, year: 1858, gregorian_year: 1858, mint_letter: null, mintage: 1500000, comment: null },
          { id: 9003, year: 1870, gregorian_year: 1870, mint_letter: "H", mintage: 100000, comment: null },
        ],
        item_type: "coin",
        details: { country: "Canada", denomination: "5 Cents", numista_id: 420, diameter_mm: "15.494", variety_notes: "KM# 2" },
        metal: { metal: "Ag", gross_weight_g: "1.167", fineness: "0.9250" },
      },
    }),
  );
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.locator("#qs-text").fill(unique("1858 Canada 5 cents"));
  await page.getByRole("button", { name: "Look this up on Numista" }).click();
  await expect(page.getByLabel("Search Numista")).toHaveValue("Canada 5 cents");
  await expect(page.getByLabel("Year", { exact: true }).first()).toHaveValue("1858");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("button", { name: /5 Cents - Victoria/ }).click();
  await expect(page.getByLabel("Which issue")).toHaveValue("9001"); // the year from the title picks it
  await page.getByRole("button", { name: "Fill in from Numista" }).click();

  await expect(page.getByLabel("Country")).toHaveValue("Canada");
  await expect(page.getByLabel("Denomination")).toHaveValue("5 Cents");
  await expect(page.getByLabel("Gross weight (g)")).toHaveValue("1.167");
  await expect(page.getByLabel("Fineness")).toHaveValue("0.925");
});

test("link an existing coin to Numista and save its estimate", async ({ page }) => {
  let patched: Record<string, unknown> | null = null;
  await page.route("**/api/v1/numista/search?*", (route) =>
    route.fulfill({ json: { count: 1, types: [{ id: 420, title: "5 Cents - Victoria", issuer: "Canada", min_year: 1858, max_year: 1901, obverse_thumbnail: null, reverse_thumbnail: null }] } }),
  );
  await page.route("**/api/v1/numista/types/420", (route) =>
    route.fulfill({
      json: {
        id: 420, url: "https://en.numista.com/420", title: "5 Cents - Victoria", issuer: "Canada", min_year: 1858, max_year: 1901,
        denomination: "5 Cents", composition: "Silver (.925)", weight_g: "1.167", size_mm: "15.494", references: ["KM# 2"],
        obverse_thumb: null, reverse_thumb: null,
        issues: [{ id: 9001, year: 1858, gregorian_year: 1858, mint_letter: null, mintage: 1500000, comment: null }],
        item_type: "coin", details: { country: "Canada", denomination: "5 Cents", numista_id: 420, diameter_mm: "15.494", variety_notes: "KM# 2" },
        metal: { metal: "Ag", gross_weight_g: "1.167", fineness: "0.9250" },
      },
    }),
  );
  await page.route("**/api/v1/items/*/numista/estimate", (route) =>
    route.fulfill({ status: 201, json: { id: 1, item_id: 1, kind: "manual", value_each: "30", currency: "USD", as_of: "2026-10-31", source: "Numista estimate (VF)", notes: null, details: null } }),
  );
  page.on("request", (r) => { if (r.method() === "PATCH" && /\/api\/v1\/items\/\d+$/.test(r.url())) patched = r.postDataJSON(); });

  const title = unique("1858 Canada 5 cents");
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Country").fill("Canada");
  await page.getByLabel("Denomination").fill("5 Cents");
  await page.getByLabel("Year").fill("1858");
  await page.getByRole("radio", { name: "Raw" }).click();
  await page.getByLabel("Grade as written").fill("VF30");
  await page.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("button", { name: "Find on Numista" }).click();
  await expect(page.getByLabel("Search Numista")).toHaveValue("Canada 5 Cents");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("button", { name: /5 Cents - Victoria/ }).click();
  await expect(page.getByLabel("Which issue")).toHaveValue("9001");
  await page.getByRole("button", { name: "Link and get estimate" }).click();
  await expect(page.getByText("Saved Numista's estimate: $30.00 each.")).toBeVisible();
  const details = (patched as unknown as { details: Record<string, unknown> }).details;
  expect(details.numista_id).toBe(420);
  expect(details.numista_issue_id).toBe(9001);
  expect(details.country).toBeUndefined(); // already filled in: left alone
  expect(details.diameter_mm).toBe("15.494"); // was blank: filled from Numista
  await expect(page.getByText("Numista N# 420")).toBeVisible();
});

test("a listing title becomes a short Numista search", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Add item" }).first().click();
  await page.locator("#qs-text").fill("2021 Silver Eagle T2 First Production PCGS MS70 Legends Life Robert Brazile");
  await expect(page.locator(".qs-found")).toContainText("American Silver Eagle");
  await page.getByRole("button", { name: "Look this up on Numista" }).click();
  await expect(page.getByLabel("Search Numista")).toHaveValue("American Silver Eagle");
  await expect(page.getByLabel("Year", { exact: true }).first()).toHaveValue("2021");
});
