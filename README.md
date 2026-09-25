# The Fragrance Gazette — automated pipeline (v3)

Everything below is automated — no hand-curation step, no "ask Claude to
refresh the content" loop. One exception, clearly marked at the bottom.

## Sources and honest confidence levels

| Section | Source | Method | Confidence |
|---|---|---|---|
| New Fragrance Launches | Now Smell This | RSS, filtered to real launch posts by URL pattern | **High** — pattern verified directly against their own master list |
| New Fragrance Launches | T3 monthly roundup | Guessed URL, price-anchor scrape | **Low** — no feed exists for this source; URL guess can miss |
| Innovation | Givaudan / IFF / Symrise / dsm-firmenich | Scraped newsroom pages, keyword-matched links | **Medium** — URLs confirmed live, exact selectors unverified |
| Innovation / Events / Trends | Nez, Fragrantica, Premium Beauty News | RSS, keyword-categorized | **Low–Medium** — feed URLs are best-guesses, see comments in script |
| Top-Buyed | FragranceX | Scraped live best-seller table | **Medium** — page confirmed accessible, parser tested on realistic fixtures only |
| Exhibitions & Diary | TrendAroma | Scraped live calendar | **Medium** — same caveat |
| Trends (Pantone / Pinterest / regional) | — | **Manual**, in `data/manual.json` | Deliberate exception — see below |

## Why one section is still manual

Pantone's Colour of the Year and Pinterest Predicts are annual reports,
not a content stream. There is nothing to poll daily — the report comes
out once a year and doesn't change until the next one does. Automating
it would mean either re-scraping the same static report every day for
no reason, or fabricating a fake "update." Neither is honest automation.
This one block in `data/manual.json` gets a manual edit when a genuinely
new report comes out — everything else runs unattended.

## An important limitation of my own testing

I validated every parser's *logic* against realistic fixture data built
from real content I fetched — that's confirmed correct (see the test
script referenced in commit history if you want to see it). What I
could **not** test is whether the live scrapers actually reach these
sites successfully, because my own development sandbox blocks all
outbound requests except to package registries — confirmed via an
`x-deny-reason: host_not_allowed` response, not the target sites
rejecting anything. GitHub Actions runners have full internet access,
so this shouldn't be an issue there — but some corporate and e-commerce
sites run bot-protection (Cloudflare, etc.) that blocks generic scraper
requests regardless of environment, and I have no way to confirm that
one way or the other from here. **The first real Actions run is the
actual test, not this README.**

## Setup — replacing an existing repo

1. Delete every file in your existing repo (or just delete the whole
   repo and start fresh — either works; a fresh repo is less error-prone).
2. Upload this entire folder's contents the same way as before: repo →
   "uploading an existing file" → select everything inside the
   extracted folder → drag in → commit.
3. Re-check Settings → Actions → General → Workflow permissions is
   still set to "Read and write permissions" (this doesn't carry over
   automatically if you started a fresh repo).
4. Re-check Settings → Pages is still set to branch `main`, folder `/docs`.
5. Actions tab → "Update Fragrance Gazette" → Run workflow, by hand.
6. **Read the log carefully this time** — it prints exactly how many
   items each source returned:
   `launches=X innovation=Y trend_items=Z bestsellers=W events=V`
   Zero anywhere tells you exactly which source to look at, not a
   vague "something's wrong."

## If a scraper returns 0 and you want to fix it yourself

- **A 403 in the log**: that source is blocking scrapers. No easy fix
  without a paid scraping service or that source's official API, if
  one exists.
- **0 items, no error**: the page loaded but the parser's assumptions
  about its structure didn't match. Look at `scrape_newsroom`,
  `scrape_trendaroma_events`, or `scrape_fragrancex_bestsellers` in
  `fetch_and_build.py` — each is a fairly short, readable function.
- **A feed shows 0 entries**: the RSS URL is wrong. See the confidence
  table above — Nez, Fragrantica, and Premium Beauty News were never
  confirmed, only guessed at reasonable WordPress-style paths.
