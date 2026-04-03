#!/usr/bin/env python3
"""
Daily Finance Digest — IB-grade market close briefing.
Triggers at 9 PM EDT (01:00 UTC) via GitHub Actions, daily.
"""

import json
import os
import re
import time
import datetime
import zoneinfo
from pathlib import Path

import feedparser
import requests

# ── Config ────────────────────────────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
BARK_KEY     = os.environ.get("BARK_KEY", "")
DIGEST_URL   = os.environ.get("DIGEST_URL", "https://subhankarshukla04.github.io/finance-digest")

_toronto = zoneinfo.ZoneInfo("America/Toronto")
TODAY    = datetime.datetime.now(_toronto).date()
DATE_STR = TODAY.strftime("%B %d, %Y")
WEEKDAY  = TODAY.strftime("%A")

EDGE_TOPICS = {
    "Monday": (
        "Private Credit Boom",
        "Private credit has grown into a $2T+ market, replacing banks as the primary lenders to mid-market companies. "
        "PE firms (Apollo, Ares, Blackstone) now control lending that banks once dominated. This shifts credit risk off "
        "regulated balance sheets and into less transparent structures. Understanding this is essential for any "
        "credit or leveraged finance role — it's one of the most significant structural changes in finance this decade.",
    ),
    "Tuesday": (
        "AI Capex vs. ROI",
        "Microsoft, Google, Meta, and Amazon are spending $300B+ combined on AI infrastructure in 2025–26. Markets "
        "have priced in transformative returns. The critical question: when does revenue justify the spend? Watch "
        "cloud revenue growth and enterprise AI adoption rates in earnings calls — those are the leading indicators "
        "Wall Street uses to validate or challenge the AI trade. The answer will define valuations for years.",
    ),
    "Wednesday": (
        "Canadian Economy & Bank of Canada",
        "Canada's economy is uniquely exposed to US trade policy, commodity cycles, and a heavily indebted consumer. "
        "The Bank of Canada often diverges from the Fed — when it does, CAD/USD moves and cross-border capital flows "
        "become the trade. Canadian banks (RBC, TD, BMO) are systemically important and proxy for housing health. "
        "For anyone in Toronto finance, understanding BoC policy vs Fed policy divergence is a core skill — it "
        "shows up in every rate desk, currency desk, and fixed income role at Bay Street firms.",
    ),
    "Thursday": (
        "Sovereign Debt Stress",
        "US debt-to-GDP sits above 120%. Japan's yield curve control is at credibility limits. Several EM economies "
        "face dollar-debt refinancing walls as rates stay higher for longer. The CBO projects US interest costs "
        "exceeding defense spending. Rising sovereign risk reprices global bonds, widens credit spreads, and "
        "affects every risk asset class — this is macro's slow-moving earthquake that everyone is watching.",
    ),
    "Friday": (
        "Deglobalization & Supply Chains",
        "Trade blocs are replacing free trade. Nearshoring, friendshoring, CHIPS Act subsidies, and export controls "
        "are forcing companies to rebuild supply chains for resilience over efficiency. This structural shift is "
        "persistently inflationary (+0.5–1% CPI), distorts FX rates, and creates long-duration capex cycles in "
        "manufacturing, semiconductors, and energy infrastructure. Every M&A deal in these sectors is affected.",
    ),
}

# ── Market Data: What IB tracks at close ─────────────────────────────────────
# (yahoo_symbol, display_name, section, is_hero)

MARKET_SYMBOLS = [
    # Hero — shown large at top
    ("^GSPC",    "S&P 500",      "hero",         True),
    ("^NDX",     "Nasdaq 100",   "hero",         True),
    ("^VIX",     "VIX",          "hero",         True),
    ("^TNX",     "10yr Yield",   "hero",         True),
    # Secondary table
    ("^DJI",     "Dow Jones",    "US Equities",  False),
    ("^RUT",     "Russell 2000", "US Equities",  False),
    ("^FVX",     "5yr Yield",    "US Rates",     False),
    ("^TYX",     "30yr Yield",   "US Rates",     False),
    ("DX-Y.NYB", "DXY",          "FX",           False),
    ("EURUSD=X", "EUR/USD",      "FX",           False),
    ("USDJPY=X", "USD/JPY",      "FX",           False),
    ("GBPUSD=X", "GBP/USD",      "FX",           False),
    ("CL=F",     "WTI Crude",    "Commodities",  False),
    ("BZ=F",     "Brent Crude",  "Commodities",  False),
    ("GC=F",     "Gold",         "Commodities",  False),
    ("HG=F",     "Copper",       "Commodities",  False),
    ("BTC-USD",  "Bitcoin",      "Crypto",       False),
]

RSS_FEEDS = [
    ("The Economist",    "https://www.economist.com/finance-and-economics/rss.xml",          3),
    ("CNBC Markets",     "https://www.cnbc.com/id/100003114/device/rss/rss.html",            4),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews",                   5),
    ("MarketWatch",      "https://feeds.marketwatch.com/marketwatch/topstories/",            4),
    ("Financial Post",   "https://financialpost.com/feed",                                   3),
    ("BNN Bloomberg",    "https://www.bnnbloomberg.ca/feed",                                 3),
]

# ── Market Data Fetching ──────────────────────────────────────────────────────

def fetch_market_data() -> dict:
    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    for symbol, name, section, is_hero in MARKET_SYMBOLS:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            meta  = r.json()["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev  = meta["chartPreviousClose"]
            pct   = ((price - prev) / prev) * 100

            if name in ("EUR/USD", "GBP/USD"):
                disp = f"{price:.4f}"
            elif name in ("VIX", "5yr Yield", "10yr Yield", "30yr Yield"):
                disp = f"{price:.2f}"
            elif price > 10000:
                disp = f"{price:,.0f}"
            else:
                disp = f"{price:,.2f}"

            results[name] = {
                "price":    price,
                "pct":      round(pct, 2),
                "positive": pct >= 0,
                "display":  disp,
                "chg":      f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                "section":  section,
                "is_hero":  is_hero,
            }
        except Exception as e:
            print(f"  [market] {name} ({symbol}) failed: {e}")
            results[name] = {
                "price": None, "pct": 0, "positive": True,
                "display": "—", "chg": "—", "section": section, "is_hero": is_hero,
            }
        time.sleep(1.5)

    return results


# ── News Fetching ─────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_newsapi() -> list:
    if not NEWS_API_KEY:
        print("  [news] NEWS_API_KEY not set, skipping")
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "markets OR economy OR fed OR inflation OR banking OR earnings OR merger OR acquisition",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 12,
                "apiKey": NEWS_API_KEY,
            },
            timeout=15,
        )
        r.raise_for_status()
        out = []
        for a in r.json().get("articles", []):
            out.append({
                "title":   a.get("title", ""),
                "snippet": (a.get("description") or "")[:500],
                "source":  a.get("source", {}).get("name", "NewsAPI"),
                "url":     a.get("url", ""),
            })
        print(f"  [news] NewsAPI: {len(out)}")
        return out
    except Exception as e:
        print(f"  [news] NewsAPI failed: {e}")
        return []


def fetch_rss() -> list:
    articles = []
    for name, url, limit in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:limit]:
                title   = entry.get("title", "").strip()
                snippet = strip_html(entry.get("summary", ""))[:500]
                link    = entry.get("link", "")
                if title:
                    articles.append({"title": title, "snippet": snippet, "source": name, "url": link})
                    count += 1
            print(f"  [rss] {name}: {count}")
        except Exception as e:
            print(f"  [rss] {name} failed: {e}")
    return articles


_PREFERRED_SOURCES = {
    "Reuters", "Reuters Business", "CNBC", "CNBC Markets", "MarketWatch",
    "Financial Post", "BNN Bloomberg", "The Economist", "Bloomberg",
    "Wall Street Journal", "Globe and Mail", "Associated Press", "Axios",
}

def dedupe(articles: list) -> list:
    seen, out = set(), []
    for a in articles:
        key = a["title"][:50].lower()
        if key not in seen:
            seen.add(key)
            out.append(a)
    # Float NA/EU sources to the top so the LLM sees them first
    out.sort(key=lambda a: 0 if a.get("source", "") in _PREFERRED_SOURCES else 1)
    return out


# ── LLM: Explain WHY, not just WHAT ──────────────────────────────────────────

def summarize(articles: list, market_data: dict) -> str:
    if not GROQ_API_KEY:
        print("  [groq] GROQ_API_KEY not set, skipping")
        return ""

    mkt = "\n".join(
        f"- {n}: {d['display']} ({d['chg']})"
        for n, d in market_data.items()
        if d["display"] != "—"
    )

    art_block = "\n\n".join(
        f"[{i+1}] {a['source'].upper()}: {a['title']}\n{a['snippet']}"
        for i, a in enumerate(articles[:22])
    )

    prompt = f"""You are a Goldman Sachs senior analyst writing the end-of-day briefing for IB analysts and finance interns.

Date: {DATE_STR} ({WEEKDAY})

MARKET CLOSE:
{mkt}

TODAY'S ARTICLES:
{art_block}

Your job is not just to say WHAT happened — explain WHY it happened, what CAUSED it, and what it MEANS. A reader should finish this briefing genuinely understanding today's market, not just knowing the headlines.

Write exactly these five sections using only facts from the articles above. Never invent data.

## WHAT MOVED MARKETS — AND WHY
3–4 sentences. Name the primary catalyst (specific data release, Fed speaker, earnings, geopolitical event). Then trace the mechanism: how did that catalyst flow through into the price moves we saw? Explain the cause-and-effect chain so a smart student can follow it. Connect at least two asset classes in your explanation.

## TOP STORIES
4 bullet points. Format: • [SOURCE] — headline context. Then one sentence explaining: what caused this, and what the downstream market effect is. Go beyond restating the headline — explain the implication.

## RATES & THE YIELD CURVE
2–3 sentences. Explain what the bond market is actually pricing in today. Is the curve steepening or flattening, and why does that matter? What does the rate move signal about where the market thinks the economy is going?

## DEALS & CORPORATE
2 sentences. Cover earnings, M&A, or notable guidance. What does this tell us about the health of the underlying sector or economy? If no deal news, say so plainly.

## WATCH TOMORROW
1 sentence. The single most important data release, event, or risk for tomorrow's session. Be specific — name the actual event if you know it.

Keep total under 450 words. Write like a thoughtful human analyst — complete sentences, no bullet-within-bullet nesting, no corporate filler."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 700,
                "temperature": 0.2,
            },
            timeout=30,
        )
        r.raise_for_status()
        result = r.json()["choices"][0]["message"]["content"]
        print("  [groq] Summary generated")
        return result
    except Exception as e:
        print(f"  [groq] Failed: {e}")
        return ""


# ── LinkedIn Editorial Series ──────────────────────────────────────────────────

CATEGORIES = {
    "rates_fed":      "Rates & The Fed — interest rate policy, yield curve, inflation, FOMC decisions",
    "private_credit": "Private Credit — direct lending, CLOs, shadow banking, non-bank lenders, credit spreads",
    "ai_capex":       "AI & Capital — hyperscaler spending, AI capex vs ROI, tech valuations, AI in finance",
    "macro_risk":     "Macro Risk — tariffs, trade wars, geopolitical events affecting markets, sovereign debt",
}

CHRONICLE_PATH = Path("docs/chronicle.json")


def load_chronicle() -> list:
    if CHRONICLE_PATH.exists():
        try:
            return json.loads(CHRONICLE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def last_post_in_category(chronicle: list, category: str) -> dict | None:
    for entry in reversed(chronicle):
        if entry.get("category") == category:
            return entry
    return None


def pick_story(articles: list, chronicle: list) -> dict:
    """Two-step: Groq picks the best category + story before we write."""
    if not GROQ_API_KEY:
        return {}

    cat_block = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    art_block = "\n\n".join(
        f"[{i+1}] {a['source'].upper()}: {a['title']}\n{a['snippet'][:300]}"
        for i, a in enumerate(articles[:20])
    )

    recent: dict[str, str] = {}
    for entry in reversed(chronicle[-20:]):
        cat = entry.get("category", "")
        if cat and cat not in recent:
            recent[cat] = entry.get("date", "")
    history_block = (
        "\n".join(f"- {k}: last written {v}" for k, v in recent.items())
        if recent else "No prior posts yet."
    )

    prompt = f"""You are an editorial assistant for a student finance content series. Pick ONE story to write about today.

FIXED CATEGORIES (pick exactly one key):
{cat_block}

RECENT HISTORY (avoid repeating the same category two days in a row if possible):
{history_block}

TODAY'S ARTICLES:
{art_block}

Pick the single most interesting, substantive story that fits one of the four categories.

PRIORITY ORDER:
1. US or Canadian market stories — Fed, S&P, TSX, Wall Street deals, Bank of Canada
2. Global or European stories with direct North American market impact
3. Stories with real data or numbers
4. Structural trends, not just one-day events

AVOID: India-specific sector stories (Indian manufacturing, RBI, rupee, Indian banking) unless they have clear, measurable impact on North American or global markets. If a US/Canadian/European story of equal quality exists, always pick that instead.

Respond with ONLY valid JSON, no explanation, no markdown:
{{"category": "<category key>", "story_headline": "<headline>", "story_summary": "<2-3 sentences: what happened and why it matters>", "key_data_point": "<one specific number or figure from the story>"}}"""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.1,
            },
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            picked = json.loads(match.group())
            print(f"  [groq] Story picked: [{picked.get('category')}] {picked.get('story_headline', '')[:60]}")
            return picked
    except Exception as e:
        print(f"  [groq] pick_story failed: {e}")
    return {}


def generate_linkedin_post(story: dict, chronicle: list) -> str:
    """Write the post in Subhankar's voice, with series framing and category callbacks."""
    if not GROQ_API_KEY or not story:
        return ""

    category  = story.get("category", "")
    cat_label = CATEGORIES.get(category, category)
    headline  = story.get("story_headline", "")
    summary   = story.get("story_summary", "")
    key_data  = story.get("key_data_point", "")
    post_count = len(chronicle) + 1  # this post will be #post_count

    prior = last_post_in_category(chronicle, category)
    prior_block = ""
    if prior:
        prior_block = f"""PRIOR POST IN THIS SERIES ({prior['date']}):
Angle covered: {prior.get('angle', '')}
Key claim: {prior.get('key_claim', '')}

If it flows naturally, reference this ("following up on something from {prior['date']}...", "been tracking this since...", "this connects back to what i wrote about..."). Don't force it if it doesn't fit today's angle."""

    if post_count == 1:
        series_context = """SERIES CONTEXT: This is post #1 — the very start of the series. Open with 1-2 casual lines before the main story: something like "starting something i've been meaning to do for a while — tracking markets daily and writing about the one thing that actually matters each day. kicking it off with [topic]." Keep it brief and genuine, then go into the story."""
    elif post_count <= 10:
        series_context = f"SERIES CONTEXT: Post #{post_count} — series is still early, a few weeks in. No need to mention it unless natural."
    else:
        series_context = f"SERIES CONTEXT: Post #{post_count} — series is established. Just write the post."

    prompt = f"""You are ghostwriting a LinkedIn post for Subhankar — a 3rd-year Rotman Commerce student (finance + economics at UofT). He tracks markets the way an IB analyst would, shares what he's learning, and is building a presence before he graduates. The frame is always: i saw this, here's how i'm thinking about it. Discovery-driven, not authority-driven.

{series_context}

TOPIC: {cat_label}
TODAY'S STORY: {headline}
WHAT HAPPENED: {summary}
KEY DATA POINT (use this): {key_data}

{prior_block}

VOICE:
- lowercase i throughout, always
- casual connective flow using "and", "so", "but" — not semicolons
- occasional natural softeners: "or something", "kind of", "which is kind of wild"
- one short punchy sentence somewhere in the middle or end
- framed as discovery: "saw this", "caught my eye", "been watching this"
- student perspective: curious, still figuring it out, not teaching anyone

STRUCTURE:
- open with where you found it and what caught your attention — one sentence
- explain what happened and why it matters in plain language
- raise a genuine question or predict what to watch next
- end with the article link on its own line
- 180–220 words total
- no hashtags
- no dashes used as connectors or separators (no " - " or " — ")

FORBIDDEN — do not use any of these under any circumstances:
delve into / at its core / it's important to note / furthermore / moreover / in conclusion / to summarize / navigate / landscape / ecosystem / leverage (verb) / excited to share / thrilled to announce / "What do you think?" / "Thoughts?" / "agree?" / hashtags / "the way you would in banking" / "running the numbers" / "tracking this in my models" / "and all that" used more than once

Output only the post text. Nothing else."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 450,
                "temperature": 0.7,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [groq] generate_linkedin_post failed: {e}")
        return ""


def append_chronicle(chronicle: list, story: dict, post_text: str) -> None:
    if any(e.get("date") == TODAY.isoformat() for e in chronicle):
        print("  chronicle: entry for today already exists, skipping duplicate")
        return
    entry = {
        "date":         TODAY.isoformat(),
        "category":     story.get("category", ""),
        "headline":     story.get("story_headline", ""),
        "angle":        story.get("story_summary", "")[:150],
        "key_claim":    story.get("key_data_point", ""),
        "post_preview": post_text[:200],
    }
    chronicle.append(entry)
    CHRONICLE_PATH.write_text(json.dumps(chronicle, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  chronicle.json updated")


# ── Design System ─────────────────────────────────────────────────────────────
# Pure dark, warm grays, restrained color — Bloomberg meets The Economist

CSS = """
:root {
  --bg:        #0a0a0a;
  --surface:   #111111;
  --surface-2: #181818;
  --border:    #222222;
  --border-2:  #2a2a2a;
  --text-1:    #f0f0f0;
  --text-2:    #888888;
  --text-3:    #444444;
  --num:       #ffffff;
  --up:        #4a7c59;
  --down:      #8b4a4a;
  --accent:    #5a8ab0;
  --green-dim: #1a3328;
  --green-txt: #7ab898;
  --green-bdr: #2a4a3a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 15px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text-1);
  max-width: 680px;
  margin: 0 auto;
  padding: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* ── Header ── */
.hdr {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 16px;
  background: var(--surface);
}
.hdr-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.hdr-eyebrow { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--accent); margin-bottom: 6px; }
.hdr-title { font-size: 22px; font-weight: 700; color: var(--text-1); letter-spacing: -0.3px; line-height: 1.2; }
.hdr-sub { font-size: 12px; color: var(--text-2); margin-top: 5px; }
.nav { display: flex; gap: 6px; flex-shrink: 0; margin-top: 2px; }
.nav a, .nav span {
  font-size: 12px;
  font-weight: 600;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-2);
  color: var(--text-2);
  text-decoration: none;
  white-space: nowrap;
  background: var(--surface-2);
}
.nav a:hover { color: var(--text-1); border-color: var(--text-3); }
.nav span { opacity: 0.35; pointer-events: none; }

/* ── Market Snapshot ── */
.mkt-wrap { margin-bottom: 16px; }
.mkt-label { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--text-3); margin-bottom: 10px; }

/* Hero grid — 4 main numbers */
.hero-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 1px;
}
.hero-cell { background: var(--surface); padding: 14px 16px; }
.hero-name { font-size: 11px; color: var(--text-2); margin-bottom: 6px; letter-spacing: 0.2px; }
.hero-price {
  font-size: 22px;
  font-weight: 700;
  color: var(--num);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.5px;
  line-height: 1;
}
.hero-chg { font-size: 12px; margin-top: 5px; font-weight: 500; }
.hero-chg.up   { color: var(--up); }
.hero-chg.down { color: var(--down); }
.hero-chg.flat { color: var(--text-3); }

/* Secondary table */
.sec-table-wrap {
  border: 1px solid var(--border);
  border-radius: 0 0 12px 12px;
  border-top: none;
  background: var(--surface);
  overflow: hidden;
}
.sec-section-hd {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-3);
  padding: 8px 16px 4px;
  background: var(--surface-2);
  border-top: 1px solid var(--border);
}
.sec-section-hd:first-child { border-top: 1px solid var(--border); }
table.sec { width: 100%; border-collapse: collapse; }
table.sec td { padding: 7px 16px; font-size: 13px; }
table.sec tr:not(:last-child) td { border-bottom: 1px solid var(--border); }
.sn { color: var(--text-2); width: 50%; }
.sv { text-align: right; font-weight: 600; color: var(--num); font-variant-numeric: tabular-nums; }
.sc { text-align: right; width: 72px; font-size: 12px; font-weight: 500; }
.sc.up   { color: var(--up); }
.sc.down { color: var(--down); }
.sc.flat { color: var(--text-3); }
.vix-bar {
  margin: 0;
  padding: 10px 16px;
  font-size: 11px;
  color: var(--text-3);
  border-top: 1px solid var(--border);
  background: var(--surface);
  border-radius: 0 0 11px 11px;
}

/* ── Analysis Sections ── */
.analysis { margin-bottom: 16px; }
.section-block {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  overflow: hidden;
  margin-bottom: 10px;
}
.section-block:last-child { margin-bottom: 0; }
.section-hd {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-3);
  padding: 12px 16px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.section-body { padding: 14px 16px; }
.section-body p {
  font-size: 14px;
  line-height: 1.72;
  color: #d8d8d8;
  margin-bottom: 10px;
}
.section-body p:last-child { margin-bottom: 0; }
.section-body .bullet {
  padding-left: 12px;
  border-left: 2px solid var(--border-2);
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.65;
  color: #d0d0d0;
}
.section-body .bullet:last-child { margin-bottom: 0; }

/* ── Edge Topic ── */
.edge {
  border: 1px solid var(--green-bdr);
  border-radius: 12px;
  background: var(--green-dim);
  overflow: hidden;
  margin-bottom: 16px;
}
.edge-hd {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #4a8a68;
  padding: 11px 16px 9px;
  border-bottom: 1px solid var(--green-bdr);
}
.edge-body { padding: 14px 16px; }
.edge-title { font-size: 15px; font-weight: 700; color: var(--green-txt); margin-bottom: 8px; letter-spacing: -0.1px; }
.edge-text { font-size: 13px; color: #7aaa8a; line-height: 1.68; }

/* ── Articles ── */
.articles {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  overflow: hidden;
  margin-bottom: 16px;
}
.articles-hd {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-3);
  padding: 12px 16px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.art {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}
.art:last-child { border-bottom: none; }
.art-source {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 5px;
}
.art-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  line-height: 1.4;
  margin-bottom: 6px;
}
.art-snippet {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.6;
  margin-bottom: 8px;
}
.art-link {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
  letter-spacing: 0.1px;
}
.art-link:hover { color: var(--text-1); }

/* ── Footer ── */
.footer {
  text-align: center;
  font-size: 11px;
  color: var(--text-3);
  padding: 16px 0 8px;
  border-top: 1px solid var(--border);
  margin-top: 4px;
  line-height: 1.6;
}

/* ── LinkedIn Post ── */
.li-post {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  overflow: hidden;
  margin-bottom: 16px;
}
.li-post-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-3);
  padding: 12px 16px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.li-copy-btn {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: none;
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  text-transform: none;
  letter-spacing: 0;
}
.li-copy-btn:hover { color: var(--text-1); border-color: var(--text-3); }
.li-post-body {
  padding: 16px;
  font-size: 14px;
  line-height: 1.8;
  color: #d8d8d8;
  white-space: pre-wrap;
}

/* ── Mobile ── */
@media (max-width: 420px) {
  body { padding: 12px; }
  .hero-price { font-size: 19px; }
  .hero-cell { padding: 12px 14px; }
}
"""


def chg_class(pct) -> str:
    if pct is None or pct == 0:
        return "flat"
    return "up" if pct > 0 else "down"


def format_summary_html(summary: str) -> str:
    if not summary:
        return ('<div class="section-block">'
                '<div class="section-hd">Analysis</div>'
                '<div class="section-body"><p style="color:var(--text-3)">Summary unavailable — see articles below.</p></div>'
                '</div>')

    blocks = []
    current_title = None
    current_lines = []

    for line in summary.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            if current_title is not None:
                blocks.append((current_title, current_lines))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title is not None:
        blocks.append((current_title, current_lines))

    html = '<div class="analysis">'
    for title, lines in blocks:
        inner = ""
        for line in lines:
            if line.startswith(("• ", "- ", "* ")):
                inner += f'<p class="bullet">{line[2:].strip()}</p>\n'
            else:
                inner += f'<p>{line}</p>\n'
        html += (f'<div class="section-block">'
                 f'<div class="section-hd">{title}</div>'
                 f'<div class="section-body">{inner}</div>'
                 f'</div>\n')
    html += '</div>'
    return html


def render_digest(market_data: dict, summary: str, articles: list,
                  prev_date: str, next_date: str, is_today: bool,
                  linkedin_post: str = "") -> str:

    edge_name, edge_body = EDGE_TOPICS.get(WEEKDAY, ("Weekend Review", "Reflect on the week's key themes."))
    summary_html = format_summary_html(summary)

    # Nav
    prev_btn = (f'<a href="{prev_date}.html">← {prev_date}</a>' if prev_date
                else '<span>← older</span>')
    next_btn = (f'<a href="{next_date}.html">{next_date} →</a>' if next_date
                else ('<a href="index.html">Today →</a>' if not is_today
                      else '<span>latest →</span>'))

    # Hero grid — 4 big numbers
    hero_names = ["S&P 500", "Nasdaq 100", "VIX", "10yr Yield"]
    hero_cells = ""
    for name in hero_names:
        d   = market_data.get(name, {})
        cls = chg_class(d.get("pct"))
        hero_cells += (
            f'<div class="hero-cell">'
            f'<div class="hero-name">{name}</div>'
            f'<div class="hero-price">{d.get("display","—")}</div>'
            f'<div class="hero-chg {cls}">{d.get("chg","—")}</div>'
            f'</div>'
        )

    # Secondary table by section
    sec_order = ["US Equities", "US Rates", "FX", "Commodities", "Crypto"]
    sec_html = ""
    for sec in sec_order:
        rows = [(sym, lbl, sect, hero)
                for sym, lbl, sect, hero in MARKET_SYMBOLS
                if sect == sec]
        if not rows:
            continue
        sec_html += f'<div class="sec-section-hd">{sec}</div><table class="sec">'
        for _, name, _, _ in rows:
            d   = market_data.get(name, {})
            cls = chg_class(d.get("pct"))
            sec_html += (
                f'<tr>'
                f'<td class="sn">{name}</td>'
                f'<td class="sv">{d.get("display","—")}</td>'
                f'<td class="sc {cls}">{d.get("chg","—")}</td>'
                f'</tr>'
            )
        sec_html += '</table>'

    vix_val  = market_data.get("VIX", {}).get("price")
    vix_note = "VIX elevated — options market is pricing meaningful near-term risk." if vix_val and vix_val > 20 else "VIX subdued — markets are calm, implied volatility is low."

    # Articles
    art_html = ""
    for a in articles[:12]:
        snippet = f'<div class="art-snippet">{a["snippet"][:280]}…</div>' if a.get("snippet") else ""
        link    = (f'<a href="{a["url"]}" target="_blank" rel="noopener" class="art-link">Read full article →</a>'
                   if a.get("url") else "")
        art_html += (
            f'<div class="art">'
            f'<div class="art-source">{a["source"][:22]}</div>'
            f'<div class="art-title">{a["title"]}</div>'
            f'{snippet}'
            f'{link}'
            f'</div>'
        )

    # LinkedIn post block
    if linkedin_post:
        escaped = linkedin_post.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        linkedin_html = f"""<div class="li-post">
  <div class="li-post-hd">
    <span>Today's LinkedIn Post</span>
    <button class="li-copy-btn" onclick="navigator.clipboard.writeText(this.dataset.post);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1800)" data-post="{escaped}">Copy</button>
  </div>
  <div class="li-post-body">{escaped}</div>
</div>"""
    else:
        linkedin_html = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0a0a">
<title>Finance Digest — {DATE_STR}</title>
<style>{CSS}</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-row">
    <div>
      <div class="hdr-eyebrow">Finance Digest</div>
      <div class="hdr-title">{DATE_STR}</div>
      <div class="hdr-sub">{WEEKDAY} &nbsp;·&nbsp; US Market Close &nbsp;·&nbsp; 4:00 PM ET</div>
    </div>
    <nav class="nav">
      {prev_btn}
      <a href="archive.html" title="Archive">☰</a>
      {next_btn}
    </nav>
  </div>
</div>

<div class="mkt-wrap">
  <div class="mkt-label">Market Snapshot</div>
  <div class="hero-grid">{hero_cells}</div>
  <div class="sec-table-wrap">
    {sec_html}
    <div class="vix-bar">{vix_note}</div>
  </div>
</div>

{summary_html}

<div class="edge">
  <div class="edge-hd">Today's Edge — {WEEKDAY}</div>
  <div class="edge-body">
    <div class="edge-title">{edge_name}</div>
    <div class="edge-text">{edge_body}</div>
  </div>
</div>

{linkedin_html}

<div class="articles">
  <div class="articles-hd">Source Articles — tap to read in full</div>
  {art_html}
</div>

<div class="footer">
  Auto-generated at market close · Toronto time &nbsp;·&nbsp; {DATE_STR}<br>
  Sources: NewsAPI · The Economist · CNBC · Google News
</div>

</body>
</html>"""


# ── Archive Page ──────────────────────────────────────────────────────────────

def build_archive() -> None:
    docs  = Path("docs")
    dated = sorted([f.stem for f in docs.glob("????-??-??.html")], reverse=True)
    total = len(dated)

    items = ""
    for date_str in dated:
        try:
            d       = datetime.date.fromisoformat(date_str)
            label   = d.strftime("%B %d, %Y")
            weekday = d.strftime("%A")
            is_today = date_str == TODAY.isoformat()
        except ValueError:
            label, weekday, is_today = date_str, "", False

        today_tag = (' <span style="font-size:10px;color:var(--accent);font-weight:700;letter-spacing:.5px">TODAY</span>'
                     if is_today else "")
        items += (
            f'<a href="{date_str}.html" class="dlink">'
            f'<span class="dday">{weekday}</span>'
            f'<span class="dlabel">{label}{today_tag}</span>'
            f'<span class="darrow">→</span>'
            f'</a>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0a0a">
<title>Finance Digest — Archive</title>
<style>
{CSS}
.dlink {{
  display: flex; align-items: center; gap: 12px;
  padding: 13px 16px; border-bottom: 1px solid var(--border);
  text-decoration: none; color: var(--text-1);
}}
.dlink:last-child {{ border-bottom: none; }}
.dlink:hover {{ background: var(--surface-2); }}
.dlink:hover .darrow {{ color: var(--text-2); }}
.dday {{ font-size: 11px; color: var(--text-3); width: 68px; flex-shrink: 0; }}
.dlabel {{ font-size: 14px; color: var(--text-2); flex: 1; font-weight: 500; }}
.darrow {{ font-size: 12px; color: var(--border-2); }}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-row">
    <div>
      <div class="hdr-eyebrow">Finance Digest</div>
      <div class="hdr-title">Archive</div>
      <div class="hdr-sub">{total} digest{"s" if total != 1 else ""} saved</div>
    </div>
    <nav class="nav"><a href="index.html">← Today</a></nav>
  </div>
</div>

<div style="border:1px solid var(--border);border-radius:12px;background:var(--surface);overflow:hidden;margin-bottom:16px;">
{items}</div>

<div class="footer">Tap any date to read that day's full digest</div>
</body>
</html>"""

    (docs / "archive.html").write_text(html, encoding="utf-8")
    print(f"  Wrote archive.html ({total} entries)")


# ── Notification ──────────────────────────────────────────────────────────────

def notify(market_data: dict) -> None:
    if not BARK_KEY:
        print("  [notify] BARK_KEY not set, skipping")
        return

    sp  = market_data.get("S&P 500",    {})
    ndx = market_data.get("Nasdaq 100", {})
    vix = market_data.get("VIX",        {})
    tnx = market_data.get("10yr Yield", {})

    body = (f"S&P {sp.get('chg','—')} · NDX {ndx.get('chg','—')} · "
            f"VIX {vix.get('display','—')} · 10yr {tnx.get('display','—')}%")

    try:
        r = requests.post(
            "https://api.day.app/push",
            json={
                "device_key": BARK_KEY,
                "title":      f"Finance Digest — {TODAY.strftime('%b %d')}",
                "body":       body,
                "url":        DIGEST_URL,
                "sound":      "minuet",
            },
            timeout=10,
        )
        r.raise_for_status()
        print(f"  [notify] {body}")
    except Exception as e:
        print(f"  [notify] Failed: {e}")


def notify_linkedin(post_text: str, story: dict) -> None:
    """Second Bark push: tap to copy the full post to clipboard."""
    if not BARK_KEY or not post_text:
        return
    category  = story.get("category", "")
    cat_label = CATEGORIES.get(category, "Finance").split("—")[0].strip()
    preview   = post_text[:140].rsplit(" ", 1)[0] + "…"
    try:
        r = requests.post(
            "https://api.day.app/push",
            json={
                "device_key": BARK_KEY,
                "title":      f"Post this on LinkedIn [{cat_label}]",
                "body":       preview,
                "copy":       post_text,
                "sound":      "telegraph",
            },
            timeout=10,
        )
        r.raise_for_status()
        print("  [notify] LinkedIn post notification sent (tap to copy)")
    except Exception as e:
        print(f"  [notify] LinkedIn notify failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"=== Finance Digest | {DATE_STR} ({WEEKDAY}) ===")

    print("[1/4] Fetching market data...")
    market_data = fetch_market_data()

    print("[2/4] Fetching news...")
    articles = dedupe(fetch_newsapi() + fetch_rss())
    print(f"  Total unique articles: {len(articles)}")

    print("[3/4] Summarizing (with cause & effect)...")
    summary = summarize(articles, market_data)

    print("[4/4] Generating LinkedIn post + rendering...")
    Path("docs").mkdir(exist_ok=True)
    docs = Path("docs")

    chronicle = load_chronicle()
    story     = pick_story(articles, chronicle)
    post      = generate_linkedin_post(story, chronicle) if story else ""

    existing     = sorted([f.stem for f in docs.glob("????-??-??.html")])
    today_str    = TODAY.isoformat()
    with_today   = sorted(set(existing + [today_str]))
    idx          = with_today.index(today_str)
    prev_date    = with_today[idx - 1] if idx > 0 else ""
    next_date    = with_today[idx + 1] if idx < len(with_today) - 1 else ""

    html = render_digest(market_data, summary, articles, prev_date, next_date,
                         is_today=True, linkedin_post=post)

    (docs / f"{today_str}.html").write_text(html, encoding="utf-8")
    (docs / "index.html").write_text(html, encoding="utf-8")
    print(f"  Wrote {today_str}.html + index.html")

    if story and post:
        (docs / "linkedin_post.txt").write_text(post, encoding="utf-8")
        print("  linkedin_post.txt written")
        append_chronicle(chronicle, story, post)
        notify_linkedin(post, story)
    elif not story:
        print("  [skip] No story selected")

    build_archive()
    notify(market_data)
    print("=== Done ===")


if __name__ == "__main__":
    main()
