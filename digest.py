#!/usr/bin/env python3
"""
Daily Finance Digest — IB-grade market close briefing.
Triggers at 4 PM ET / 9:30 PM IST via GitHub Actions.
"""

import os
import re
import time
import datetime
from pathlib import Path

import feedparser
import requests

# ── Config ────────────────────────────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
BARK_KEY     = os.environ.get("BARK_KEY", "")
DIGEST_URL   = os.environ.get("DIGEST_URL", "https://subhankarshukla04.github.io/finance-digest")

TODAY    = datetime.date.today()
DATE_STR = TODAY.strftime("%B %d, %Y")
WEEKDAY  = TODAY.strftime("%A")

EDGE_TOPICS = {
    "Monday": (
        "Private Credit Boom",
        "Private credit has grown into a $2T+ market, replacing banks as the primary lenders to mid-market companies. "
        "PE firms (Apollo, Ares, Blackstone) now control lending that banks once dominated. This shifts credit risk off "
        "regulated balance sheets and into less transparent structures. Understanding this matters for any credit or "
        "leveraged finance role.",
    ),
    "Tuesday": (
        "AI Capex vs. ROI",
        "Microsoft, Google, Meta, and Amazon are spending $300B+ combined on AI infrastructure in 2025–26. Markets "
        "have priced in transformative returns. The critical question: when does revenue justify the spend? Watch "
        "cloud revenue growth and enterprise AI adoption rates in earnings calls — those are the leading indicators "
        "Wall Street uses to validate or challenge the AI trade.",
    ),
    "Wednesday": (
        "India & Southeast Asia Capital Flows",
        "India's equity market crossed $4T in market cap. FII inflows, the manufacturing shift from China, and a "
        "600M+ middle class are creating a multi-decade structural story. Key sectors: infrastructure, financials, "
        "consumer. Southeast Asia (Vietnam, Indonesia) is the supply chain beneficiary. This is where long-duration "
        "EM capital is moving.",
    ),
    "Thursday": (
        "Sovereign Debt Stress",
        "US debt-to-GDP sits above 120%. Japan's yield curve control is at credibility limits. Several EM economies "
        "face dollar-debt refinancing walls as rates stay higher for longer. CBO projects US interest costs exceeding "
        "defense spending. Rising sovereign risk reprices global bonds, widens spreads, and affects every risk asset "
        "class — this is macro's slow-moving earthquake.",
    ),
    "Friday": (
        "Deglobalization & Supply Chains",
        "Trade blocs are replacing free trade. Nearshoring, friendshoring, CHIPS Act subsidies, and export controls "
        "are forcing companies to rebuild supply chains for resilience over efficiency. This shift is persistently "
        "inflationary (+0.5–1% CPI), distorts FX, and creates long-duration capex cycles in manufacturing, semis, "
        "and energy infrastructure.",
    ),
}

# ── Market Data: Everything Wall Street Tracks ────────────────────────────────
# Organized into sections. (symbol, display_name, section, unit_suffix)

MARKET_SYMBOLS = [
    # US Equities
    ("^GSPC",     "S&P 500",      "US Equities",      ""),
    ("^NDX",      "Nasdaq 100",   "US Equities",      ""),
    ("^DJI",      "Dow Jones",    "US Equities",      ""),
    ("^RUT",      "Russell 2000", "US Equities",      ""),
    # US Rates
    ("^FVX",      "5yr Yield",    "US Rates",         "%"),
    ("^TNX",      "10yr Yield",   "US Rates",         "%"),
    ("^TYX",      "30yr Yield",   "US Rates",         "%"),
    # FX
    ("DX-Y.NYB",  "DXY",         "FX",               ""),
    ("EURUSD=X",  "EUR/USD",     "FX",               ""),
    ("USDJPY=X",  "USD/JPY",     "FX",               ""),
    ("GBPUSD=X",  "GBP/USD",     "FX",               ""),
    # Commodities
    ("CL=F",      "WTI Crude",   "Commodities",      ""),
    ("BZ=F",      "Brent Crude", "Commodities",      ""),
    ("GC=F",      "Gold",        "Commodities",      ""),
    ("HG=F",      "Copper",      "Commodities",      ""),
    # Volatility & Crypto
    ("^VIX",      "VIX",         "Vol & Crypto",     ""),
    ("BTC-USD",   "Bitcoin",     "Vol & Crypto",     ""),
]

RSS_FEEDS = [
    ("The Economist",          "https://www.economist.com/finance-and-economics/rss.xml",                                              3),
    ("CNBC Markets",           "https://www.cnbc.com/id/100003114/device/rss/rss.html",                                               4),
    ("Google News — Markets",  "https://news.google.com/rss/search?q=financial+markets+economy+fed+rates+treasury&hl=en-US&gl=US&ceid=US:en", 5),
    ("Google News — Deals",    "https://news.google.com/rss/search?q=merger+acquisition+IPO+earnings+wall+street&hl=en-US&gl=US&ceid=US:en",  3),
    ("Google News — AI/Banks", "https://news.google.com/rss/search?q=AI+JPMorgan+Goldman+Sachs+Morgan+Stanley+banking&hl=en-US&gl=US&ceid=US:en", 3),
]

# ── Market Data Fetching ──────────────────────────────────────────────────────

def fetch_market_data() -> dict:
    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    for symbol, name, section, unit in MARKET_SYMBOLS:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            meta  = r.json()["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev  = meta["chartPreviousClose"]
            pct   = ((price - prev) / prev) * 100

            # Format price nicely
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
                "arrow":    "▲" if pct >= 0 else "▼",
                "display":  disp + unit,
                "chg":      f"{'▲' if pct >= 0 else '▼'} {abs(pct):.2f}%",
                "positive": pct >= 0,
                "section":  section,
            }
        except Exception as e:
            print(f"  [market] {name} ({symbol}) failed: {e}")
            results[name] = {
                "price": None, "pct": 0, "arrow": "", "display": "N/A",
                "chg": "—", "positive": True, "section": section,
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
                "snippet": (a.get("description") or "")[:400],
                "source":  a.get("source", {}).get("name", "NewsAPI"),
                "url":     a.get("url", ""),
            })
        print(f"  [news] NewsAPI: {len(out)} articles")
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
                snippet = strip_html(entry.get("summary", ""))[:400]
                link    = entry.get("link", "")
                if title:
                    articles.append({"title": title, "snippet": snippet, "source": name, "url": link})
                    count += 1
            print(f"  [rss] {name}: {count}")
        except Exception as e:
            print(f"  [rss] {name} failed: {e}")
    return articles


def dedupe(articles: list) -> list:
    seen, out = set(), []
    for a in articles:
        key = a["title"][:50].lower()
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


# ── LLM Summarization — IB-Grade Prompt ──────────────────────────────────────

def summarize(articles: list, market_data: dict) -> str:
    if not GROQ_API_KEY:
        print("  [groq] GROQ_API_KEY not set, skipping")
        return ""

    mkt = "\n".join(
        f"- {n}: {d['display']} ({d['chg']})"
        for n, d in market_data.items()
        if d["display"] != "N/A"
    )

    art_block = "\n\n".join(
        f"[{i+1}] {a['source'].upper()}: {a['title']}\n{a['snippet']}"
        for i, a in enumerate(articles[:22])
    )

    prompt = f"""You are a Goldman Sachs markets associate writing the end-of-day briefing for analysts and IB interns.

Date: {DATE_STR} ({WEEKDAY})

MARKET CLOSE DATA:
{mkt}

TODAY'S NEWS:
{art_block}

Write exactly these five sections. Be sharp, specific, and direct — like a real sell-side note. Only use facts from the articles above. Never invent data or quotes.

## MACRO & RATE MOVES
3 sentences max. What drove rates today? Any Fed speakers, inflation data, or economic releases? What is the yield curve signaling?

## TOP STORIES
Exactly 4 bullet points. Format: • [SOURCE] Title — one sentence on why it matters for markets or deals.

## DEALS & CORPORATE
2–3 sentences. Earnings beats/misses, notable M&A, IPO activity, guidance changes. If none in articles, say "No major deal activity in today's feed."

## AI & TECH IN FINANCE
2 sentences. Any AI story touching banks, trading desks, or fintech. If none, say "No major AI-finance stories today."

## ONE THING FOR TOMORROW
1 sentence. The single most important event, data release, or risk for tomorrow's trading session.

Keep total under 420 words. Write like a human analyst, not a chatbot."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 650,
                "temperature": 0.25,
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


# ── HTML Rendering ────────────────────────────────────────────────────────────

SHARED_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;max-width:700px;margin:0 auto;padding:16px;}
.hdr{background:linear-gradient(135deg,#1e3a5f 0%,#0f2d4a 100%);border-radius:14px;padding:18px 20px;margin-bottom:12px}
.hdr-row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.hdr-title{font-size:19px;font-weight:700;color:#93c5fd}
.hdr-sub{font-size:12px;color:#64748b;margin-top:4px}
.nav-btns{display:flex;gap:6px;flex-shrink:0}
.nav-btn{background:#1e3a5f;color:#93c5fd;border:1px solid #2d5a8e;border-radius:8px;padding:5px 11px;font-size:12px;font-weight:600;text-decoration:none;white-space:nowrap;}
.nav-btn:hover{background:#2d5a8e}
.nav-btn.dim{color:#475569;border-color:#1e293b;pointer-events:none}
.card{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:12px}
.section-label{font-size:10px;font-weight:700;color:#475569;letter-spacing:1.2px;text-transform:uppercase;margin:14px 0 6px}
.section-label:first-child{margin-top:0}
table{width:100%;border-collapse:collapse}
.mn{padding:6px 0;color:#94a3b8;font-size:13px}
.mv{padding:6px 0;text-align:right;font-weight:600;font-size:14px;font-variant-numeric:tabular-nums}
.mc{padding:6px 0;text-align:right;font-size:12px;width:76px}
.vix-note{margin-top:8px;font-size:11px;color:#475569;border-top:1px solid #334155;padding-top:8px}
.ai-section{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:10px}
.ai-section h3{font-size:10px;font-weight:700;color:#64748b;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:9px;padding-bottom:6px;border-bottom:1px solid #334155}
.ai-section p{font-size:14px;line-height:1.65;color:#cbd5e1;margin-bottom:7px}
.ai-section .bullet{border-left:2px solid #2d5a8e;padding-left:10px;margin-bottom:8px;color:#cbd5e1}
.edge{background:linear-gradient(135deg,#14271f,#0d1f17);border:1px solid #166534;border-radius:12px;padding:16px;margin-bottom:12px}
.elabel{font-size:10px;color:#4ade80;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:5px}
.etitle{font-size:15px;font-weight:700;color:#86efac;margin-bottom:7px}
.ebody{font-size:13px;color:#a7f3d0;line-height:1.65}
.artcard{background:#1e293b;border-radius:12px;padding:14px 16px;margin-bottom:12px}
.art-item{padding:11px 0;border-bottom:1px solid #1e293b}
.art-item:not(:last-child){border-bottom:1px solid #334155}
.art-meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}
.stag{display:inline-block;background:#172d47;color:#60a5fa;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;letter-spacing:.3px}
.art-title{font-size:14px;color:#e2e8f0;font-weight:500;line-height:1.4;margin-bottom:5px}
.art-snippet{font-size:12px;color:#64748b;line-height:1.5;margin-bottom:6px}
.read-link{font-size:12px;color:#60a5fa;text-decoration:none;font-weight:500}
.read-link:hover{color:#93c5fd;text-decoration:underline}
.footer{text-align:center;font-size:11px;color:#475569;padding:12px 0 4px}
"""


def format_summary_html(summary: str) -> str:
    if not summary:
        return '<div class="ai-section"><p style="color:#64748b;">Summary unavailable. See articles below.</p></div>'

    html = ""
    in_block = False
    for line in summary.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            if in_block:
                html += "</div>\n"
            html += f'<div class="ai-section"><h3>{line[3:].strip()}</h3>\n'
            in_block = True
        elif line.startswith(("• ", "- ", "* ")):
            html += f'<p class="bullet">→ {line[2:].strip()}</p>\n'
        else:
            html += f'<p>{line}</p>\n'
    if in_block:
        html += "</div>\n"
    return html


def mrow(name: str, data: dict) -> str:
    d = data.get(name, {})
    # Rates and FX are neutral color; equities green/red; others grey
    section = d.get("section", "")
    if section == "US Rates" or section == "FX":
        color = "#94a3b8"
    elif section == "Vol & Crypto" and name == "VIX":
        color = "#f59e0b"
    else:
        color = "#4ade80" if d.get("positive", True) else "#f87171"
    return (
        f'<tr><td class="mn">{name}</td>'
        f'<td class="mv">{d.get("display","N/A")}</td>'
        f'<td class="mc" style="color:{color}">{d.get("chg","—")}</td></tr>'
    )


def render_digest(market_data: dict, summary: str, articles: list,
                  prev_date: str, next_date: str, is_today: bool) -> str:

    edge_name, edge_body = EDGE_TOPICS.get(WEEKDAY, ("Weekend Review", "Reflect on the week's key themes."))
    summary_html = format_summary_html(summary)

    vix_val  = market_data.get("VIX", {}).get("price")
    vix_mood = "elevated — markets are nervous" if vix_val and vix_val > 20 else "calm — low fear"

    # Nav buttons
    prev_btn = (f'<a href="{prev_date}.html" class="nav-btn">← {prev_date}</a>' if prev_date
                else '<span class="nav-btn dim">← older</span>')
    next_btn = (f'<a href="{next_date}.html" class="nav-btn">{next_date} →</a>' if next_date
                else ('<a href="index.html" class="nav-btn">Today →</a>' if not is_today
                      else '<span class="nav-btn dim">latest →</span>'))

    # Articles HTML — each card with title, snippet, and "Read full article →"
    art_items = ""
    for a in articles[:12]:
        snippet_html = f'<div class="art-snippet">{a["snippet"][:220]}…</div>' if a.get("snippet") else ""
        read_link    = (f'<a href="{a["url"]}" target="_blank" rel="noopener" class="read-link">Read full article →</a>'
                        if a.get("url") else "")
        art_items += f"""<div class="art-item">
  <div class="art-meta"><span class="stag">{a['source'][:20]}</span></div>
  <div class="art-title">{a['title']}</div>
  {snippet_html}
  {read_link}
</div>\n"""

    # Market table by section
    sections_order = ["US Equities", "US Rates", "FX", "Commodities", "Vol & Crypto"]
    mkt_html = ""
    for sec in sections_order:
        names_in_sec = [n for n, s, _, _ in [(sym, d["section"], None, None)
                        for sym, lbl, sec2, _ in MARKET_SYMBOLS
                        for n, d in [(lbl, market_data.get(lbl, {}))]
                        if d.get("section") == sec]]
        # simpler approach
        names_in_sec = [lbl for _, lbl, sec2, _ in MARKET_SYMBOLS if sec2 == sec]
        rows = "".join(mrow(n, market_data) for n in names_in_sec)
        mkt_html += f'<div class="section-label">{sec}</div><table>{rows}</table>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance Digest — {DATE_STR}</title>
<style>{SHARED_CSS}</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-row">
    <div>
      <div class="hdr-title">Finance Digest</div>
      <div class="hdr-sub">{DATE_STR} &nbsp;·&nbsp; {WEEKDAY} &nbsp;·&nbsp; US Market Close</div>
    </div>
    <div class="nav-btns">
      {prev_btn}
      <a href="archive.html" class="nav-btn">📚</a>
      {next_btn}
    </div>
  </div>
</div>

<div class="card">
  <div class="section-label" style="margin-top:0">📊 Market Snapshot</div>
  {mkt_html}
  <div class="vix-note">VIX {market_data.get("VIX",{}).get("display","—")} — {vix_mood}</div>
</div>

{summary_html}

<div class="edge">
  <div class="elabel">💡 Today's Edge — {WEEKDAY}</div>
  <div class="etitle">{edge_name}</div>
  <div class="ebody">{edge_body}</div>
</div>

<div class="artcard">
  <div class="section-label" style="margin-top:0">📰 Source Articles — tap to read full</div>
  {art_items}
</div>

<div class="footer">
  Auto-generated at US market close &nbsp;·&nbsp; {DATE_STR}<br>
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
            badge   = (' <span style="background:#1e3a5f;color:#93c5fd;font-size:10px;'
                       'padding:2px 7px;border-radius:10px;margin-left:6px">today</span>'
                       if date_str == TODAY.isoformat() else "")
        except ValueError:
            label, weekday, badge = date_str, "", ""

        items += f"""<a href="{date_str}.html" class="dlink">
  <span class="dday">{weekday}</span>
  <span class="dlabel">{label}{badge}</span>
  <span class="darrow">→</span>
</a>\n"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance Digest — Archive</title>
<style>
{SHARED_CSS}
.dlink{{display:flex;align-items:center;gap:10px;padding:13px 0;border-bottom:1px solid #334155;text-decoration:none}}
.dlink:last-child{{border-bottom:none}}
.dlink:hover .dlabel{{color:#93c5fd}}
.dday{{font-size:11px;color:#475569;width:68px;flex-shrink:0}}
.dlabel{{font-size:14px;color:#cbd5e1;font-weight:500;flex:1}}
.darrow{{font-size:13px;color:#334155}}
.dlink:hover .darrow{{color:#60a5fa}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-row">
    <div>
      <div class="hdr-title">📚 Digest Archive</div>
      <div class="hdr-sub">{total} digest{"s" if total != 1 else ""} saved</div>
    </div>
    <a href="index.html" class="nav-btn">← Today</a>
  </div>
</div>

<div class="card">
{items}</div>

<div class="footer">Tap any date to read that day's digest</div>

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

    body = (
        f"S&P {sp.get('chg','—')} | NDX {ndx.get('chg','—')} | "
        f"VIX {vix.get('display','—')} | 10yr {tnx.get('display','—')}%"
    )

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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"=== Finance Digest | {DATE_STR} ({WEEKDAY}) ===")

    print("[1/4] Fetching market data...")
    market_data = fetch_market_data()

    print("[2/4] Fetching news...")
    articles = dedupe(fetch_newsapi() + fetch_rss())
    print(f"  Total unique articles: {len(articles)}")

    print("[3/4] Summarizing...")
    summary = summarize(articles, market_data)

    print("[4/4] Rendering + saving...")
    Path("docs").mkdir(exist_ok=True)
    docs = Path("docs")

    # Get sorted list of existing dated files for prev/next nav
    existing = sorted([f.stem for f in docs.glob("????-??-??.html")])
    today_str = TODAY.isoformat()

    # Add today to the list if not already there (for nav calc)
    if today_str not in existing:
        existing_with_today = sorted(existing + [today_str])
    else:
        existing_with_today = existing

    idx      = existing_with_today.index(today_str)
    prev_date = existing_with_today[idx - 1] if idx > 0 else ""
    next_date = existing_with_today[idx + 1] if idx < len(existing_with_today) - 1 else ""

    html = render_digest(market_data, summary, articles, prev_date, next_date, is_today=True)

    dated_path = docs / f"{today_str}.html"
    dated_path.write_text(html, encoding="utf-8")
    (docs / "index.html").write_text(html, encoding="utf-8")
    print(f"  Wrote {dated_path.name} + index.html")

    build_archive()
    notify(market_data)
    print("=== Done ===")


if __name__ == "__main__":
    main()
