#!/usr/bin/env python3
"""
Fragrance Gazette — automated builder (v3).

Goal, stated plainly: combine several sources into one page with NO
manual curation step. Every section below is either an RSS feed or a
scraper that runs unattended on GitHub's schedule. Confidence varies
by source — noted per source, because "automated" and "guaranteed to
work" are not the same claim, and I'm not pretending otherwise.

Category filtering (the "just the important ones" ask) is done by
keyword rules, not a human — see CATEGORY_KEYWORDS. That means it will
misfile things sometimes. That's the honest cost of removing the human.
"""
import json, datetime, html, re
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
MANUAL_PATH = ROOT / "data" / "manual.json"      # ONLY thing left non-automated — see bottom
TEMPLATE_PATH = ROOT / "template.html"
OUT_PATH = ROOT / "docs" / "index.html"
UA = {"User-Agent": "Mozilla/5.0 (compatible; FragranceGazetteBot/1.0; +https://github.com)"}

# --- RSS sources ---------------------------------------------------------
FEEDS = [
    {"url": "https://nstperfume.com/feed/", "name": "Now Smell This", "force_category": None},
    {"url": "https://mag.bynez.com/feed/", "name": "Nez", "force_category": None},          # moderate confidence
    {"url": "https://www.fragrantica.com/rss/news.xml", "name": "Fragrantica", "force_category": None},  # low confidence
    {"url": "https://www.premiumbeautynews.com/xml/syndication.rss", "name": "Premium Beauty News", "force_category": None},  # low confidence
]

# Now Smell This tags every genuine new-launch post with one of these
# URL-slug endings (verified directly against their own master list page,
# https://nstperfume.com/new-perfumes-fragrances/ — every single entry
# there ends this way). Anything else from their feed (reviews, essays,
# reader polls) gets filtered OUT, which is the actual "don't repeat
# everything" ask, done by a rule instead of a human.
NST_LAUNCH_SLUG = re.compile(r"-new-(fragrances?|perfumes?)/?$", re.I)

# --- Newsroom scrapers (generic: keyword-matched links) ------------------
# Medium confidence — I confirmed each URL loads and lists real news, but
# I have not confirmed these exact selectors against live markup (see
# scrape_newsroom). A wrong guess here just yields 0 items, logged, not a crash.
NEWSROOMS = [
    {"url": "https://www.givaudan.com/media/media-releases", "name": "Givaudan"},
    {"url": "https://www.iff.com/media/news", "name": "IFF"},
    {"url": "https://www.symrise.com/newsroom/", "name": "Symrise"},                 # unconfirmed URL
    {"url": "https://www.dsm-firmenich.com/corporate/news.html", "name": "dsm-firmenich"},  # unconfirmed URL
]
KEYWORDS = ["fragrance", "scent", "perfume", "aroma", "olfact", "ingredient", "molecule"]

# --- Bespoke scrapers (higher confidence — built against real fetched content) ---
TRENDAROMA_URL = "https://www.trendaroma.com/fragrance-calendar/"
FRAGRANCEX_URL = "https://www.fragrancex.com/shopping/best-selling-perfumes"

# --- T3 monthly roundup (lowest confidence — guessed URL, no feed exists) ---
T3_PATTERN = "https://www.t3.com/home-living/beauty/mens-fragrance-launches-{month}-2026"

CATEGORY_KEYWORDS = {
    "launch": ["launch", "debut", "unveil", "new fragrance", "new perfume", "new scent",
               "eau de parfum", "eau de toilette", "flanker"],
    "innovation": ["molecule", "biotech", "technology", "ingredient", "patent",
                   "sustainab", "artificial intelligence", " ai ", "material", "innovation"],
    "event": ["congress", "expo", "summit", "fair", "exhibition", "museum", " week "],
    "trend": ["trend", "pantone", "pinterest", "color of the year", "colour of the year"],
}

def strip_tags(t):
    return re.sub(r"<[^<]+?>", "", t or "").strip()

def categorize(text):
    t = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return None  # no match = dropped, not shown

def fetch_rss(feed):
    out = []
    try:
        parsed = feedparser.parse(feed["url"])
        if not parsed.entries:
            print(f"[warn] {feed['name']}: 0 entries — feed URL may be wrong")
            return out
        for e in parsed.entries[:40]:
            title = html.unescape(e.get("title", "")); link = e.get("link", "#")
            summary = html.unescape(strip_tags(e.get("summary", "")))[:220]
            if feed["name"] == "Now Smell This":
                if not NST_LAUNCH_SLUG.search(link):
                    continue  # not a launch post — drop
                cat = "launch"
            else:
                cat = categorize(f"{title} {summary}")
                if cat is None:
                    continue
            out.append({"title": title, "link": link, "summary": summary,
                        "source": feed["name"], "category": cat})
    except Exception as ex:
        print(f"[warn] {feed['name']} RSS failed: {ex}")
    return out

def scrape_newsroom(nr):
    out = []
    try:
        r = requests.get(nr["url"], headers=UA, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if not (20 <= len(text) <= 160):
                continue
            if not any(k in text.lower() for k in KEYWORDS):
                continue
            href = a["href"]
            if href.startswith("/"):
                base = re.match(r"https?://[^/]+", nr["url"]).group(0)
                href = base + href
            if href in seen:
                continue
            seen.add(href)
            out.append({"title": text, "link": href, "summary": "",
                        "source": nr["name"], "category": "innovation"})
        if not out:
            print(f"[warn] {nr['name']} newsroom: 0 matching items — selectors may need updating")
    except Exception as ex:
        print(f"[warn] {nr['name']} newsroom scrape failed: {ex}")
    return out[:8]

def page_lines(url):
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n")
    return [l.strip() for l in text.split("\n") if l.strip()]

def scrape_trendaroma_events(limit=12):
    try:
        lines = page_lines(TRENDAROMA_URL)
    except Exception as ex:
        print(f"[warn] TrendAroma scrape failed: {ex}")
        return []
    events = []
    for i, line in enumerate(lines):
        if line.startswith("📍") or "📍" in line:
            location = line.replace("📍", "").strip()
            date_line = lines[i - 1] if i >= 1 else ""
            name_line = lines[i - 2] if i >= 2 else ""
            if name_line and date_line:
                events.append({"name": name_line, "date": date_line, "location": location})
    if not events:
        print("[warn] TrendAroma: 0 events parsed — page structure may have changed")
    return events[:limit]

def scrape_fragrancex_bestsellers(limit=20):
    try:
        lines = page_lines(FRAGRANCEX_URL)
    except Exception as ex:
        print(f"[warn] FragranceX scrape failed: {ex}")
        return []
    results, i = [], 0
    while i < len(lines) and len(results) < limit:
        if lines[i].isdigit() and 1 <= int(lines[i]) <= 100:
            rank = int(lines[i])
            for j in range(i + 1, min(i + 6, len(lines))):
                if " by " in lines[j] and len(lines[j]) < 150:
                    results.append({"rank": rank, "name": lines[j]})
                    i = j
                    break
        i += 1
    if not results:
        print("[warn] FragranceX: 0 items parsed — page structure may have changed")
    return results

def scrape_t3():
    """Best-effort: T3 has no feed, so we guess this/last month's URL slug.
    Weakest link in the pipeline — a wrong guess just yields nothing."""
    now = datetime.date.today()
    candidates = [now.strftime("%B").lower(),
                  (now.replace(day=1) - datetime.timedelta(days=1)).strftime("%B").lower()]
    out = []
    for month in candidates:
        url = T3_PATTERN.format(month=month)
        try:
            r = requests.get(url, headers=UA, timeout=15)
            if r.status_code != 200:
                continue
            lines = page_lines(url)
            for i, line in enumerate(lines):
                if re.search(r"[£$€]\d", line) and i >= 2:
                    name_line = lines[i - 2]
                    if 8 <= len(name_line) <= 90 and name_line[0].isupper():
                        out.append({"title": name_line, "link": url, "summary": "",
                                    "source": "T3", "category": "launch"})
        except Exception as ex:
            print(f"[warn] T3 ({month}) fetch failed: {ex}")
    return out[:10]

def render_list(items, empty_msg):
    if not items:
        return f'<p class="warn">{empty_msg}</p>'
    out = []
    for i in items:
        summary = f'{i["summary"]} ' if i.get("summary") else ""
        out.append(f'<div class="item"><div class="meta sans">{i["source"]}</div>'
                    f'<h3>{i["title"]}</h3><p>{summary}<a href="{i["link"]}">Source</a></p></div>')
    return "\n".join(out)

def render_bestsellers(items):
    if not items:
        return '<p class="warn">Could not reach FragranceX this run — see build log.</p>'
    rows = "".join(f"<tr><td>{i['rank']}</td><td>{i['name']}</td></tr>" for i in items)
    return f'<table><tr><th>#</th><th>Fragrance</th></tr>{rows}</table>'

def render_events(items):
    if not items:
        return '<p class="warn">Could not parse TrendAroma this run — see build log.</p>'
    rows = "".join(f"<tr><td>{e['name']}</td><td>{e['location']}</td><td>{e['date']}</td></tr>" for e in items)
    return f'<table><tr><th>Event</th><th>Where</th><th>When</th></tr>{rows}</table>'

def main():
    all_items = []
    for f in FEEDS:
        all_items += fetch_rss(f)
    for nr in NEWSROOMS:
        all_items += scrape_newsroom(nr)
    all_items += scrape_t3()

    launches = [i for i in all_items if i["category"] == "launch"]
    innovation = [i for i in all_items if i["category"] == "innovation"]
    trend_items = [i for i in all_items if i["category"] == "trend"]

    bestsellers = scrape_fragrancex_bestsellers()
    events = scrape_trendaroma_events()

    manual = {}
    if MANUAL_PATH.exists():
        manual = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    trend_note = manual.get("trend_note", "")  # Pantone / Pinterest / regional table — see note below

    static_html = f"""
<h2><span>New Fragrance Launches</span></h2>
<div class="warn">Auto-filtered from Now Smell This (by URL pattern — high confidence) and T3
(by guessed monthly URL — lowest confidence in this pipeline). No human picks these; a keyword
or URL rule does.</div>
{render_list(launches, "Nothing matched this run. Either quiet feeds or a rule needs adjusting — check the build log.")}

<h2><span>Innovation</span></h2>
<div class="warn">Scraped from Givaudan, IFF, Symrise and dsm-firmenich newsroom pages (medium
confidence — selectors unverified against live markup, see README) plus Nez/Fragrantica items
matching innovation keywords.</div>
{render_list(innovation, "Nothing matched this run — check the build log for which newsroom scrapers returned 0.")}

<h2><span>Top-Buyed</span></h2>
<div class="warn">Scraped live from FragranceX's best-seller tracker. Real sales rank, one
retailer only.</div>
{render_bestsellers(bestsellers)}

<h2><span>Exhibitions &amp; Diary</span></h2>
<div class="warn">Scraped live from TrendAroma's calendar. Perfumeaholic blocks automated
access entirely (robots.txt) — cannot be added regardless of confidence level.</div>
{render_events(events)}

<h2><span>Trends</span></h2>
<div class="warn"><strong>The one section that isn't feed-driven, on purpose.</strong>
Pantone's Colour of the Year and Pinterest Predicts are annual reports, not a content stream —
there's nothing to poll daily. {"Feed-matched trend items below, if any turned up this run." if trend_items else ""}</div>
{render_list(trend_items, "")}
{trend_note}
"""

    today = datetime.date.today().strftime("%d %B %Y")
    tmpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    out = tmpl.replace("{{DATE}}", today).replace("{{STATIC}}", static_html)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(out, encoding="utf-8")

    print(f"Wrote {OUT_PATH} — dated {today}")
    print(f"  launches={len(launches)} innovation={len(innovation)} "
          f"trend_items={len(trend_items)} bestsellers={len(bestsellers)} events={len(events)}")

if __name__ == "__main__":
    main()
