#!/usr/bin/env python3
"""
Daily Finance Digest
Runs at US market close (4 PM ET / 9:30 PM IST) via GitHub Actions.
Scrapes news + market data → summarizes with Groq → publishes to GitHub Pages → notifies via Simplepush.
"""

import os
import re
import time
import datetime
from pathlib import Path

import feedparser
import requests

# ── Config ────────────────────────────────────────────────────────────────────

GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
NEWS_API_KEY  = os.environ.get("NEWS_API_KEY", "")
BARK_KEY       = os.environ.get("BARK_KEY", "")
DIGEST_URL    = os.environ.get("DIGEST_URL", "https://your-username.github.io/finance-digest")

TODAY    = datetime.date.today()
DATE_STR = TODAY.strftime("%B %d, %Y")
WEEKDAY  = TODAY.strftime("%A")

EDGE_TOPICS = {
    "Monday": (
        "Private Credit Boom",
        "Private credit has grown into a $2T+ market, replacing banks as the primary lenders "
        "to mid-market companies. PE firms and asset managers now control loans that banks once "
        "dominated. This shifts credit risk off bank balance sheets — but concentrates it in less "
        "regulated hands. Key players: Apollo, Ares, Blackstone.",
    ),
    "Tuesday": (
        "AI Capex vs. ROI",
        "Microsoft, Google, Meta, and Amazon are collectively spending $300B+ on AI infrastructure. "
        "Markets have priced in transformative returns. The question every analyst asks: when does "
        "revenue justify the spend? Watch cloud revenue growth rates and enterprise AI adoption in "
        "earnings calls — those are the leading indicators.",
    ),
    "Wednesday": (
        "India & Southeast Asia Capital Flows",
        "India's equity market crossed $4T in market cap. FII inflows, the manufacturing shift away "
        "from China, and a growing middle class are driving a multi-decade structural story. Key "
        "sectors attracting capital: infrastructure, financials, consumer discretionary. Southeast "
        "Asia (Vietnam, Indonesia) is the supply chain beneficiary.",
    ),
    "Thursday": (
        "Sovereign Debt Stress",
        "US debt-to-GDP sits above 120%. Japan continues managing its yield curve at the limit of "
        "credibility. Several EM economies face dollar-debt refinancing walls as rates stay higher "
        "for longer. Rising sovereign risk reprices global bonds, widens spreads, and affects every "
        "risk asset. The CBO projects US interest costs exceeding defense spending by 2025.",
    ),
    "Friday": (
        "Deglobalization & Supply Chains",
        "Trade blocs are replacing free trade. Nearshoring, friendshoring, the CHIPS Act, and "
        "export controls are forcing companies to rebuild supply chains for resilience over efficiency. "
        "This structural shift is persistently inflationary (+0.5–1% CPI), distorts FX, and creates "
        "long-duration capex cycles in manufacturing, semiconductors, and energy.",
    ),
}

RSS_FEEDS = [
    ("The Economist",        "https://www.economist.com/finance-and-economics/rss.xml",                                        3),
    ("CNBC Markets",         "https://www.cnbc.com/id/100003114/device/rss/rss.html",                                          4),
    ("Google News — Markets","https://news.google.com/rss/search?q=financial+markets+economy+fed+rates&hl=en-US&gl=US&ceid=US:en", 5),
    ("Google News — AI/Finance","https://news.google.com/rss/search?q=AI+artificial+intelligence+banks+finance+JPMorgan+Goldman&hl=en-US&gl=US&ceid=US:en", 3),
]

MARKET_SYMBOLS = [
    ("S&P 500",   "^GSPC"),
    ("10yr Yield","^TNX"),
    ("DXY",       "DX-Y.NYB"),
    ("WTI Crude", "CL=F"),
    ("VIX",       "^VIX"),
]

# ── Market Data ───────────────────────────────────────────────────────────────

def fetch_market_data() -> dict:
    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    for name, symbol in MARKET_SYMBOLS:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev  = meta["chartPreviousClose"]
            pct   = ((price - prev) / prev) * 100
            results[name] = {
                "price":          round(price, 2),
                "change_pct":     round(pct, 2),
                "arrow":          "▲" if pct >= 0 else "▼",
                "display":        f"{price:,.2f}",
                "change_display": f"{'▲' if pct >= 0 else '▼'} {abs(pct):.2f}%",
                "positive":       pct >= 0,
            }
        except Exception as e:
            print(f"  [market] {name} failed: {e}")
            results[name] = {
                "price": None, "change_pct": 0, "arrow": "",
                "display": "N/A", "change_display": "—", "positive": True,
            }
        time.sleep(2)

    return results


# ── News ──────────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_newsapi() -> list:
    articles = []
    if not NEWS_API_KEY:
        print("  [news] NEWS_API_KEY not set, skipping NewsAPI")
        return articles
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "markets OR economy OR fed OR inflation OR banking OR earnings",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "apiKey": NEWS_API_KEY,
            },
            timeout=15,
        )
        r.raise_for_status()
        for a in r.json().get("articles", []):
            articles.append({
                "title":   a.get("title", ""),
                "snippet": (a.get("description") or "")[:300],
                "source":  a.get("source", {}).get("name", "NewsAPI"),
                "url":     a.get("url", ""),
            })
        print(f"  [news] NewsAPI: {len(articles)} articles")
    except Exception as e:
        print(f"  [news] NewsAPI failed: {e}")
    return articles


def fetch_rss() -> list:
    articles = []
    for source_name, url, limit in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:limit]:
                title = entry.get("title", "").strip()
                snippet = strip_html(entry.get("summary", ""))[:300]
                link = entry.get("link", "")
                if title:
                    articles.append({"title": title, "snippet": snippet, "source": source_name, "url": link})
                    count += 1
            print(f"  [rss] {source_name}: {count} articles")
        except Exception as e:
            print(f"  [rss] {source_name} failed: {e}")
    return articles


def dedupe(articles: list) -> list:
    seen, unique = set(), []
    for a in articles:
        key = a["title"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


# ── Summarization ─────────────────────────────────────────────────────────────

def summarize(articles: list, market_data: dict) -> str:
    if not GROQ_API_KEY:
        print("  [groq] GROQ_API_KEY not set, skipping summarization")
        return ""

    market_lines = "\n".join(
        f"- {name}: {d['display']} ({d['change_display']})"
        for name, d in market_data.items()
    )

    article_block = "\n\n".join(
        f"[{i+1}] {a['source'].upper()}: {a['title']}\n{a['snippet']}"
        for i, a in enumerate(articles[:20])
    )

    prompt = f"""You are a senior Goldman Sachs analyst writing a concise daily briefing for a finance student.

Today: {DATE_STR} ({WEEKDAY})

MARKET CLOSE:
{market_lines}

TODAY'S ARTICLES:
{article_block}

Write exactly these four sections. Be sharp. Only use facts from the articles above — never invent.

## TOP STORIES
• [source] headline — why it matters for markets (one sentence each, 3 bullets)

## MACRO & RATES
2–3 sentences on what central banks/bonds are signaling today.

## AI IN FINANCE
1–2 sentences on any AI/tech story touching banks or markets. If none in articles, say "No major AI-finance stories today."

## MARKET CLOSE READ
2–3 sentences interpreting today's price action in context of the news.

Keep total under 380 words."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.3,
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

def format_summary_html(summary: str) -> str:
    if not summary:
        return '<div class="section"><p style="color:#64748b;">Summary unavailable today. See source articles below.</p></div>'

    html = ""
    in_section = False
    for line in summary.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            if in_section:
                html += "</div>\n"
            title = line[3:].strip()
            html += f'<div class="section"><h3>{title}</h3>\n'
            in_section = True
        elif line.startswith(("• ", "- ", "* ")):
            html += f'<p class="bullet">→ {line[2:].strip()}</p>\n'
        else:
            html += f'<p>{line}</p>\n'
    if in_section:
        html += "</div>\n"
    return html


def render_html(market_data: dict, summary: str, articles: list) -> str:
    edge_name, edge_body = EDGE_TOPICS.get(WEEKDAY, ("Weekend", "Reflect on the week's themes."))
    summary_html = format_summary_html(summary)

    def mrow(name: str) -> str:
        d = market_data.get(name, {})
        color = "#4ade80" if d.get("positive", True) else "#f87171"
        if name in ("DXY", "VIX"):
            color = "#94a3b8"
        return (
            f'<tr><td class="mn">{name}</td>'
            f'<td class="mv">{d.get("display","N/A")}</td>'
            f'<td class="mc" style="color:{color}">{d.get("change_display","—")}</td></tr>'
        )

    vix_val = market_data.get("VIX", {}).get("price")
    vix_mood = "elevated — markets are nervous" if vix_val and vix_val > 20 else "calm — low fear"

    articles_html = "".join(
        f'<a href="{a["url"]}" target="_blank" class="alink">'
        f'<span class="stag">{a["source"][:18]}</span>{a["title"]}</a>\n'
        for a in articles[:10]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance Digest — {DATE_STR}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;max-width:660px;margin:0 auto;padding:16px;}}
.hdr{{background:linear-gradient(135deg,#1e3a5f 0%,#0f2d4a 100%);border-radius:14px;padding:20px 20px 16px;margin-bottom:14px}}
.hdr-top{{display:flex;justify-content:space-between;align-items:flex-start}}
.hdr-title{{font-size:20px;font-weight:700;color:#93c5fd;letter-spacing:.3px}}
.hdr-sub{{font-size:12px;color:#64748b;margin-top:5px}}
.archive-btn{{background:#1e3a5f;color:#93c5fd;border:1px solid #2d5a8e;border-radius:8px;padding:6px 12px;font-size:12px;font-weight:600;text-decoration:none;white-space:nowrap;}}
.archive-btn:hover{{background:#2d5a8e}}
.card{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:12px}}
.clabel{{font-size:11px;font-weight:700;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse}}
.mn{{padding:7px 0;color:#94a3b8;font-size:14px}}
.mv{{padding:7px 0;text-align:right;font-weight:600;font-size:15px;font-variant-numeric:tabular-nums}}
.mc{{padding:7px 0;text-align:right;font-size:13px;width:80px}}
.vix-note{{margin-top:8px;font-size:11px;color:#475569}}
.section{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:10px}}
.section h3{{font-size:11px;font-weight:700;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;border-bottom:1px solid #334155;padding-bottom:6px}}
.section p{{font-size:14px;line-height:1.65;color:#cbd5e1;margin-bottom:7px}}
.section .bullet{{padding-left:2px;border-left:2px solid #334155;padding-left:10px;margin-bottom:8px}}
.edge{{background:linear-gradient(135deg,#14271f,#0d1f17);border:1px solid #166534;border-radius:12px;padding:16px;margin-bottom:12px}}
.elabel{{font-size:11px;color:#4ade80;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:5px}}
.etitle{{font-size:15px;font-weight:700;color:#86efac;margin-bottom:8px}}
.ebody{{font-size:13px;color:#a7f3d0;line-height:1.65}}
.artcard{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:12px}}
.alink{{display:block;padding:9px 0;border-bottom:1px solid #334155;color:#cbd5e1;text-decoration:none;font-size:13px;line-height:1.45}}
.alink:last-child{{border-bottom:none}}
.alink:hover{{color:#93c5fd}}
.stag{{display:inline-block;background:#172d47;color:#60a5fa;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;margin-right:6px;white-space:nowrap;vertical-align:middle}}
.footer{{text-align:center;font-size:11px;color:#475569;padding:14px 0 6px}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-top">
    <div>
      <div class="hdr-title">Finance Digest</div>
      <div class="hdr-sub">{DATE_STR} &nbsp;·&nbsp; {WEEKDAY} &nbsp;·&nbsp; US Market Close</div>
    </div>
    <a href="archive.html" class="archive-btn">📚 Archive</a>
  </div>
</div>

<div class="card">
  <div class="clabel">📊 Market Snapshot</div>
  <table>
    {mrow("S&P 500")}
    {mrow("10yr Yield")}
    {mrow("DXY")}
    {mrow("WTI Crude")}
    {mrow("VIX")}
  </table>
  <div class="vix-note">VIX {market_data.get("VIX",{}).get("display","—")} — {vix_mood}</div>
</div>

{summary_html}

<div class="edge">
  <div class="elabel">💡 Today's Edge — {WEEKDAY}</div>
  <div class="etitle">{edge_name}</div>
  <div class="ebody">{edge_body}</div>
</div>

<div class="artcard">
  <div class="clabel">📰 Source Articles</div>
  {articles_html}
</div>

<div class="footer">
  Auto-generated at US market close &nbsp;·&nbsp; {DATE_STR}<br>
  Sources: NewsAPI · The Economist · CNBC · Google News
</div>

</body>
</html>"""


# ── Archive ───────────────────────────────────────────────────────────────────

def build_archive() -> None:
    docs = Path("docs")
    dated = sorted(
        [f.stem for f in docs.glob("????-??-??.html")],
        reverse=True,
    )

    items_html = ""
    for date_str in dated:
        try:
            d = datetime.date.fromisoformat(date_str)
            label   = d.strftime("%B %d, %Y")
            weekday = d.strftime("%A")
            is_today = date_str == TODAY.isoformat()
            badge = ' <span style="background:#1e3a5f;color:#93c5fd;font-size:10px;padding:2px 7px;border-radius:10px;margin-left:6px;">today</span>' if is_today else ""
        except ValueError:
            label, weekday, badge = date_str, "", ""

        items_html += f"""<a href="{date_str}.html" class="dlink">
  <span class="dday">{weekday}</span>
  <span class="dlabel">{label}{badge}</span>
</a>\n"""

    total = len(dated)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance Digest — Archive</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;max-width:660px;margin:0 auto;padding:16px;}}
.hdr{{background:linear-gradient(135deg,#1e3a5f 0%,#0f2d4a 100%);border-radius:14px;padding:20px;margin-bottom:14px}}
.hdr-top{{display:flex;justify-content:space-between;align-items:center}}
.hdr-title{{font-size:20px;font-weight:700;color:#93c5fd}}
.hdr-sub{{font-size:12px;color:#64748b;margin-top:5px}}
.back-btn{{background:#1e3a5f;color:#93c5fd;border:1px solid #2d5a8e;border-radius:8px;padding:6px 12px;font-size:12px;font-weight:600;text-decoration:none;}}
.back-btn:hover{{background:#2d5a8e}}
.card{{background:#1e293b;border-radius:12px;padding:4px 16px;margin-bottom:12px}}
.dlink{{display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid #334155;text-decoration:none;}}
.dlink:last-child{{border-bottom:none}}
.dlink:hover .dlabel{{color:#93c5fd}}
.dday{{font-size:11px;color:#475569;width:70px;flex-shrink:0}}
.dlabel{{font-size:14px;color:#cbd5e1;font-weight:500}}
.count{{font-size:12px;color:#475569;text-align:center;padding:10px 0 4px}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-top">
    <div>
      <div class="hdr-title">📚 Digest Archive</div>
      <div class="hdr-sub">{total} digest{"s" if total != 1 else ""} saved</div>
    </div>
    <a href="index.html" class="back-btn">← Today</a>
  </div>
</div>

<div class="card">
{items_html}</div>

</body>
</html>"""

    (docs / "archive.html").write_text(html, encoding="utf-8")
    print(f"  Wrote docs/archive.html ({total} entries)")


# ── Notification ──────────────────────────────────────────────────────────────

def notify(market_data: dict) -> None:
    if not BARK_KEY:
        print("  [notify] BARK_KEY not set, skipping")
        return

    sp  = market_data.get("S&P 500",   {})
    vix = market_data.get("VIX",       {})
    tnx = market_data.get("10yr Yield",{})

    body = (
        f"S&P {sp.get('change_display','—')} | "
        f"VIX {vix.get('display','—')} | "
        f"10yr {tnx.get('display','—')}%"
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
        print(f"  [notify] Sent: {body}")
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
    html = render_html(market_data, summary, articles)
    Path("docs").mkdir(exist_ok=True)
    dated_file = Path("docs") / f"{TODAY.isoformat()}.html"
    dated_file.write_text(html, encoding="utf-8")
    Path("docs/index.html").write_text(html, encoding="utf-8")
    print(f"  Wrote docs/index.html + {dated_file.name}")

    build_archive()
    notify(market_data)
    print("=== Done ===")


if __name__ == "__main__":
    main()
