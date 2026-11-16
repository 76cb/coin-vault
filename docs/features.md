# Features

Everything Coin Vault does, area by area. The [README](../README.md) has the short version and the screenshots.

## Contents

- [Sign-in and access](#sign-in-and-access)
- [Items](#items)
- [Quick add and the title reader](#quick-add-and-the-title-reader)
- [Reference compositions and the world catalogue](#reference-compositions-and-the-world-catalogue)
- [Mint and proof sets](#mint-and-proof-sets)
- [Photos](#photos)
- [Bulk upload](#bulk-upload)
- [Photo library](#photo-library)
- [Photo editor](#photo-editor)
- [Documents](#documents)
- [Spot prices and melt value](#spot-prices-and-melt-value)
- [Market values](#market-values)
- [PCGS](#pcgs)
- [Numista](#numista)
- [Weekly value updates](#weekly-value-updates)
- [Photo AI](#photo-ai)
- [Goldbacks](#goldbacks)
- [Dashboard and value history](#dashboard-and-value-history)
- [Collection page](#collection-page)
- [Tools](#tools)
- [Exports and the insurance report](#exports-and-the-insurance-report)
- [Data providers](#data-providers)
- [Backups](#backups)
- [Appearance](#appearance)
- [Operations](#operations)

## Sign-in and access

- **One admin account** with argon2id passwords. Server-side sessions use an HttpOnly cookie, and every change needs a CSRF token. Repeated failed logins are throttled.
- **Read-only logins** (Settings): a login for a spouse, heir or insurer that sees everything and can change nothing.
- **API tokens:** scoped (`items:read`, `items:write`, `prices:read`, `export`), with optional expiry and revocation. They are meant for scripts and other tools on your LAN. Writes with a token do not need the CSRF header; browser sessions do.

## Items

- **Types:** coin, bullion coin or round, mint set, bar, banknote, Goldback, junk/constant-content lot and other, each with its own fields.
- **Condition** is raw (Sheldon grade or descriptive) or slabbed (company, grade, cert number, designations such as CAC). For PCGS and NGC certs the item links to the grading service's own lookup page.
- **Metal content** is entered per piece. Pure troy ounces are computed from gross weight × fineness, and you can override them. Gross weight can be typed in grams, troy ounces, pennyweight, grains or kilograms (fractions like 1/10 work); it is stored in grams. Bars convert g, ozt, kg and tola.
- **US base-metal coins** (zinc cents, nickels, clad dimes, quarters, halves and dollars) get their composition and weight filled in from the date and denomination, from the US Mint's specifications and Wikipedia for earlier years. The 1982 cent says to weigh it; the 1942–1945 silver nickels and the silver issues use their silver reference instead.
- **Purchase price** is optional: mark a cost as known, estimated or unknown. Each item also has a storage location (nested), tags, status and sale details.
- **Valuation rule** per item: the higher of melt and market (the default), melt, market or what you paid.
- **Edits are protected against conflicts.** If you edit an item in two browser tabs, the second save is refused rather than silently overwriting the first.
- **History:** every change to a value-affecting field is recorded in the item's history: quantity, price, fees, status, sale, grade, metal content and valuation rule.
- **On an item:** what you paid over (or under) today's melt value, and what is still missing (metal, cost, photos or value).
- **Duplicate** starts a new item with the same details and metal but no price, cert or photos.

## Quick add and the title reader

Paste a listing title ("2021 $1 Silver Eagle T2 First Production PCGS MS70") and the form fills in type, year, product or series, grading company, grade, designations, quantity and the matching reference composition. You check it, add the price, and save. Rarely used fields sit under "More details".

The title reader recognises foreign coins ("1937 Great Britain half crown", "1922 Mexico 2 pesos gold", "Swiss 20 francs Vreneli"), bullion sizes ("1/10 oz Gold Libertad", "30 g Gold Panda"), refiners' bars ("Geiger 100 g silver bar"), Goldbacks ("10 x 1/2 Goldback Nevada 2021") and mint sets ("2008 United States 50 State Quarters Silver Proof Set").

A round or bar that is not in the reference list gets its metal from the weight and fineness in the title or stamped on it ("1 TROY OZ .999 FINE SILVER"). A bullion bar or round with a weight but no fineness written is taken as .999 (.9995 for platinum and palladium) and says the fineness was assumed; anything else with no fineness is left for you to fill in. A US coin struck for circulation in base metal (a 2000 dollar, a 1971 dollar) is not offered silver figures unless the title says silver.

## Reference compositions and the world catalogue

- **About 700 reference compositions** are built in, and you can add your own. Type to search them on the item form.
- **US and bullion:** US 90/40/35% silver, pre-1933 US gold, major bullion coins (Eagles, Maples including fractional gold, Britannias, Philharmonics, Krugerrands, Kookaburra, Kangaroo, Sovereigns, 100 Corona, Palladium Eagle) and bars from Valcambi (including CombiBars), PAMP Suisse, Argor-Heraeus, Heraeus, Perth Mint, Royal Canadian Mint, The Royal Mint, Austrian Mint, Sunshine, Asahi and Geiger Edelmetalle (silver .999 from 1 g to 5 kg, gold .9999 from 1 g to 1 kg, and the 25 × 1 g Multicards). Refiners not yet verified (Metalor, Credit Suisse, Engelhard, Johnson Matthey and others) are suggested as names, with the fineness typed in.
- **World catalogue** (`backend/app/data/catalogue/*.json`, one file per region and batch, about 470 rows): early US silver and gold by weight standard, commemoratives, the Trade dollar and $3 gold; UK and Commonwealth pre-decimal silver; Canada, Newfoundland, Mexico (pesos, gold pesos, Libertads) and Latin America; France, Switzerland, Germany, Austria, the Netherlands, Italy, Belgium, Spain, Sweden, Norway, Denmark, Finland, Hungary, Greece, Portugal and Russia; Chinese dragon dollars and Pandas, Japan, the Philippines, Iran and Ottoman gold; and world bullion lines in every size (Britannia, Kangaroo, Lunar, Koala, Kookaburra, Libertad, Krugerrand, Platinum Eagle, Queen's Beasts and more).
- **Every row cites its source.** Each names the page its weight and fineness came from, with any caveat in its citation. Rows that could not be checked against a source were left out rather than guessed. Poland, Czechoslovakia and most of South America are not covered yet.
- **Suggestions on the form:** the item form suggests a composition from country, denomination, year, mint mark and title. When the details fit more than one (an 1881 dollar could be silver or gold), it lists them all.
- **Junk silver and gold lots** are valued by face value × the composition's pure ounces per $1, including a worn-90% figure.

## Mint and proof sets

A set is one item (one price, one set of photos, one market value) with every coin inside it listed.

- Paste or photograph "2008 United States 50 State Quarters Silver Proof Set" and the five quarters are filled in by name, each with its weight and fineness; the set's silver is the sum of its coins (0.9042 ozt for that one), so melt value follows.
- **Built in:** US proof sets 1936–1941 and 1950–2025, silver proof sets 1992–2025, the quarters-only proof sets (clad and silver) from 1999, and Uncirculated Coin Sets 1999–2025 with their Philadelphia and Denver coins, with the quarters, Presidential dollars, 2004–2005 nickels and 2009 cents named. Coins with no silver are listed with what they are made of. Prestige and Limited Edition sets, the 1942 sets and other countries' sets are saved as sets and their coins typed in ("Add a coin").
- Searching the collection for a coin ("Oklahoma", "Presidential", "Kennedy") finds the set it is in and says which coin matched. The CSV export and insurance report list the coins.
- On the form, "Fill in this year's coins" fills the list from the year and kind of set. Any coin can be edited, removed or added; a set with no coins listed keeps a metal figure typed for the whole set.
- Silver proof sets saved earlier as a coin are converted on update, unless their silver had been typed by hand.

## Photos

Several per item, with roles (obverse, reverse, edge, slab front, slab back, other). You can reorder them and choose a cover. On upload:

- The file type is checked from its content, not its extension, and size is capped.
- GPS location is removed losslessly from JPEGs. HEIC from phones becomes a high-quality JPEG.
- Photos are auto-rotated for display and get thumbnails.
- Each is checked for blur, glare, low resolution and dark exposure, with advice on retaking.
- Possible duplicates are flagged: an exact match, or a near match by perceptual hash.

On a phone, **Take a photo** under any photo drop zone opens the camera. Collection tiles fill the square edge to edge; Settings, Appearance can switch to showing the whole photo instead.

## Bulk upload

Drop a batch from your camera.

- Files named like `0042_obv.jpg` / `0042_rev.jpg` (also `_o`/`_r`, `-front`/`-back`, `_edge`, `_slab_front`, `_slab_back`) are paired by name. Everything else is paired in upload order.
- You can split, merge or re-role a group.
- Then save each group as a new item or add it to an existing one.
- With Photo AI set up, **Identify all** scans every waiting group in turn; "Create N items as read" saves them all, or check and save them one by one.

## Photo library

The Photos page shows every photo you have uploaded, each once, newest first, filtered by on items or not. Choose one to see which items use it, and put it on any item (as obverse, reverse and so on, optionally the cover). On an item, "Choose from your photos" does the same. The file is shared, never copied, and stays as long as any item or upload uses it.

**Create an item from photos:** press Select photos, pick an item's photos (each shows the order you picked it in), and press Create an item. Add item opens with those photos, each with its side (taken from the upload's file names when they say, otherwise front, back, then other in the order picked), which you can change, reorder or leave out. Saving puts them on the new item, the obverse as cover, and takes them out of the upload queue.

Delete a photo from its panel, or use Select photos to delete many at once: it comes off every item it is on (after a confirmation listing them) and out of any waiting bulk upload, and the file is removed.

## Photo editor

On an item, Edit on any photo opens it full screen.

- **Crop** (free, circle, square with a circle guide, 4:3, 3:4, 3:2 or the original shape), turn, mirror, straighten, and adjust brightness, contrast, saturation, warmth and sharpness.
- **Non-destructive.** The uploaded file is never changed; the edits are saved as settings and the thumbnails are rendered from the original, so Reset to original always works.
- **Circle** cuts the coin out: everything outside the circle becomes clear (transparent, so the coin sits on any background), white or black, with a smooth edge.
- **Find the coin** locates the coin's rim in the photo (also inside a slab) and fits the circle to it; drag it if it is not quite right.
- **Find the slab** finds a grading holder's outline and squares it up: a holder photographed at an angle comes out as an upright rectangle filling the frame. **Fix tilt** does the same by hand: drag four corners onto anything that should be rectangular.
- Opening a photo shows the edited version at full size (a PNG when the background is clear); the original stays downloadable.

## Documents

Receipts, invoices, certificates and assay cards (PDF or image), linked to one or more items. They are served only to the signed-in owner.

## Spot prices and melt value

- Gold, silver, platinum and palladium are fetched every 15 minutes (configurable) from [gold-api.com](https://gold-api.com), which needs no key.
- gold-api.com's platinum and palladium had stopped updating when checked (Sep 17 and Oct 16, 2026), so every price is judged by its own timestamp. Out-of-date metals come from [Metal Sentinel](https://metal-sentinel.com) (free RapidAPI key, 7,500 requests a month), then [Metals.Dev](https://metals.dev) (free key, 100 a month).
- Backups are asked only for the metals still missing, and their calls are paced so the free allowance lasts the month.
- Polling pauses while the metals markets are closed (Friday 5 pm to Sunday 6 pm New York time), and a price older than the stale threshold is marked stale.
- A price is stored only if it parses as a positive number; a failed or malformed answer moves on to the next provider and is logged.
- The header shows the latest prices and when they were fetched.
- **Melt value** is quantity × pure ounces × spot, per metal. Items without metal content have no melt value rather than zero.
- **Price alerts:** a level per metal, above or below, checked every time prices are fetched; a notice stays at the top of every page until dismissed. There is no email or push notification.

## Market values

On an item, under Market value:

- **Search sold listings** searches recent eBay sales through your SoldComps key (one request per search), shows each sale with photo, date and price, and saves the median of the ones you tick, with or without shipping.
- **Enter a value** records a dealer quote, price guide or appraisal with its date and source.
- **PCGS price guide** (PCGS-graded items with a cert number) looks the cert up and saves today's PCGS price guide value, with the population, as a market value.
- **Which value counts:** the newest by date, except that on a slabbed coin a Numista estimate (Numista prices raw coins in G to Unc bands) is only used when there is nothing else. "Use this" on any value in the list makes it the one used, whatever its date; "Undo choice" goes back to the automatic choice. Older values stay in the list.

## PCGS

- **Cert lookup:** type or paste a PCGS cert number into the quick add box and press Look up. PCGS's name, grade, designations, cert, PCGS number and metal weight fill the form, and you can save its price guide value as the market value. It uses the [PCGS Public API](https://www.pcgs.com/publicapi) with your own access token (free, 1,000 calls a day; the app stops at a cap you set, 900 by default).
- **By number and grade, or by barcode:** type a PCGS number and grade ("9801 MS65", "PCGS #7126 64+") into the quick add box, or use Look up at PCGS for a PCGS or NGC holder's barcode (typed, scanned with a barcode scanner, or read from a photo of the label on the server). By number and grade works for any coin, raw or graded by anyone, and gives the PCGS price guide value for that grade.
- On an item with a PCGS number and a grade but no PCGS cert (an NGC slab, say), the PCGS price guide button looks it up the same way. A graded coin with no PCGS number yet (from ICG or ANACS, say) gets the same button: give its PCGS number (there is a search link to find it on PCGS CoinFacts) and it is kept on the item. The price is PCGS's for a PCGS-graded coin in that grade.

## Numista

With your Numista API key (Settings, Data providers), the quick add box has "Look this up on Numista". It searches the world catalogue from the country and denomination it read in your title (or anything you type), shows matches with photos (coins whose years include yours first, and Type 2 first when your title says T2), lists only that year's issues with the best fit marked (by mint mark, and proof, burnished or MS as your grade and title say), and fills in country, denomination, year, mint mark, weight, fineness, diameter and the KM number.

On any coin's page, "Find on Numista" under Market value searches from the item's own country, denomination and year and links the coin (filling only blank details, and the metal if there is none); with a grade it saves the estimate in the same step. "Get Numista's estimate" saves Numista's price for that year and grade (G to Unc) in your currency. Coin details are cached for 30 days, so looking at the same coin again uses no requests; the app stops at 1,800 requests a month by default (the free plan allows 2,000).

## Weekly value updates

Settings, admins: once a week (Sunday 05:40 by default, changeable) the PCGS price guide values and Numista estimates you have fetched are fetched again. A changed value is saved as a new dated market value, so the value history shows it; an unchanged one is marked as checked. Only items that already have a value from that source are followed, so no lookups are spent on items you have not asked about. A value you chose with Use this stays chosen. Each source stops for the week if its cap is reached. Update now runs it straight away.

## Photo AI

Optional; an admin sets it up in Settings, AI. A vision model running on your own network through [Ollama](https://ollama.com) looks at an item's photos. Photos go only to that server. See [install.md](install.md#photo-ai-ollama-on-the-gpu) for setting up the server.

- **What is it?** On Add item (with photos chosen), on each bulk-upload group, and on an item's page, Identify from the photos reads the date, mint mark, denomination and design and fills the form the same way the quick add box does, metal content included. On an item it fills only what is empty; the title, prices and notes stay. On a bulk-upload group, Use this takes everything the scan read, and Create item saves it all in one step: details, grade and metal. Check the details first opens Add item with everything filled and the photos attached, for when you want to look before saving.
- **Holders:** in a slab, it reads the label (service, grade, cert number, PCGS number) and any barcode, and offers the PCGS lookup, whose details are the most reliable.
- **What grade?** On a raw coin's page, Suggest a grade gives a grade range (like VF20 to VF30) with what it saw: wear, surfaces, any problems that would make it a Details grade, and what other photos would help. It is a guess from photos, not a grade. Add to the item's notes keeps it, dated.
- **Pieces you already have:** each answer lists items you hold with the same year, design (or denomination) and mint mark, and any item that already has one of these photos.

## Goldbacks

On the Goldbacks page, pick the state or series, set how many of each denomination you have (with what you paid, if you like), and save; each denomination becomes an item with its count. The gold is worked out from the denomination (1/1000 troy oz of 24-karat gold per Goldback, so a 5 holds 0.005 oz), so melt value follows the gold price. The page shows what you hold by series and denomination: notes, Goldbacks, gold and melt. Series and denominations are from Wikipedia's Goldback article; "Another" takes any series not listed. The app draws plain cards rather than Goldback's own artwork, which is theirs; add your own photos to any of them.

## Dashboard and value history

- **Dashboard:** total melt value, what you paid (known and estimated, with a count of items with no cost), gain on items that have both, pure ounces by metal, what you paid over today's melt in total, and your average cost per ounce by metal next to spot.
- **Value history:** what the collection was worth on each day, over a month, three months, a year or everything, with a dashed line for what you had paid. Each day counts what you held then (from the acquired date to the sale date) at that day's spot price and the market values you had recorded by then, so today's point matches the dashboard. Filter by kind of item or metal.
- A chart of the spot price, or of what your holdings would have been worth, over a day to a year.
- Breakdowns by metal, type and storage location.

## Collection page

- Search by title, year, country, cert number or a coin inside a set; filter by type, metal, status, location and tag.
- A **Needs attention** filter (items with no metal, cost, photos or value; each item's page says what is still to add).
- Sorting by recently changed or added, title, year, acquired date, value, melt, gain or what you paid.
- **Select** to move, tag, re-status, mark as seen or delete several items at once.

## Tools

- **Series checklists:** 50 State, DC and Territories, America the Beautiful and American Women quarters, Presidential dollars, Morgan and Peace dollars and Franklin halves by date and mint, and Silver Eagles by year. A coin counts by its year, mint mark (where the series is collected by mint) and the design's name in its title or series; coins inside mint sets count. The Morgan, Peace and Franklin date lists are from general knowledge, checked only by their totals (96, 24, 35).
- **Want list:** what you are looking for, with a target price. "Add to want list" on any missing checklist coin; "Got it" opens Add item and marks it found when saved.
- **Sales and gains:** every sold item with proceeds (price less selling fees), cost and gain, totalled by year and split by whether it was held over a year. A record for tax preparation, not tax advice.
- **Price alerts:** see [Spot prices](#spot-prices-and-melt-value).
- **Inventory check:** pick a location and tick each piece as you see it; the date shows on the item as "Last seen".
- **Storage labels:** printable labels with a QR code that opens that location's contents (the phone must be on your network and signed in). Only the location's name is printed.
- **Import a spreadsheet:** a CSV with at least a Title column; titles are read like the quick add box. It previews every row before anything is saved, and takes this app's own CSV export back in. Photos are not imported.

## Exports and the insurance report

- **Export CSV** (Collection page): every item matching the page's filters, one row each, with every field: details, grade and cert, pure ounces per metal, melt, market and current values (and where the value came from), purchase and sale details, location and tags. Opens in Excel, Numbers or Google Sheets; text that looks like a formula is kept as text.
- **Insurance report** (Collection page): a printable inventory of what you hold (sold items left out): total value, value by location, the spot prices used, and each item with its photos, description, grade, cert or serial numbers, metal content, location, acquired date and value with its source. Order it by value, location, title or date acquired, and choose whether to show photos and what you paid. Print it, or choose "Save as PDF" as the printer.

## Data providers

In Settings, each provider has a key field, a test button, an on/off switch and a monthly request cap.

- Keys are encrypted (AES-GCM) before they are stored and are never returned by the API; only the last four characters are shown.
- Usage is counted on every call and, where the provider reports it, synced from the provider's own figures daily and when you press Test. The provider's count wins.
- The usage meter turns amber at 80% of the cap and red at the cap, where calls stop until the period resets. Daily counts and the last calls are listed.
- SoldComps usage is read from its headers after every search and from its free usage endpoint daily and on Test.

## Backups

Coin Vault backs itself up every night at 03:15 (change the time, or turn it off, in Settings, Backups). An update backs up first too, and Settings has **Back up now** and **Download** for any backup as one `.tar`. What a backup holds, where it goes, how many are kept and how to restore are in [install.md](install.md#backups-and-restore).

## Appearance

Light and dark follow your device by default; the moon and sun button in the header or Settings, Appearance switches it, and the choice is remembered in that browser. Collection tiles can fill the square or show the whole photo.

## Operations

Migrations run on startup, and there is a health endpoint (`/api/v1/health`, plus `/api/v1/health/ready` when signed in). Logs are structured JSON with secrets redacted. The interactive API reference is at `http://<host>/api/v1/docs`.
