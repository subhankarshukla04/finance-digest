# Finance Digest

A one-page market close I read every night at 9 pm Toronto time. It has run since late March 2026, and every past edition is kept.

Live: https://subhankarshukla04.github.io/finance-digest/ (archive at `/archive.html`)

## What's on the page

- **The close.** S&P 500, Nasdaq 100, VIX and the 10-year at the top. Under them: the Dow and Russell 2000, the 5- and 30-year yields, DXY and three FX pairs, WTI, Brent, gold, copper and Bitcoin. Prices come from Yahoo Finance.
- **What moved it.** A short summary of the day's headlines, written as cause and effect ("yields rose on X, so Y sold off") rather than a list of stories. It is drafted by Llama 3.3 70B on Groq from the day's articles and the closing numbers.
- **The articles.** Deduplicated headlines from The Economist, CNBC, Reuters, MarketWatch, Financial Post and BNN Bloomberg, plus NewsAPI.
- **One topic per weekday.** Private credit on Monday, AI capex against returns on Tuesday, the Bank of Canada against the Fed on Wednesday, sovereign debt on Thursday, supply chains on Friday. I wrote these to keep one structural theme in view each week.

## How it runs

`digest.py` is one script. A GitHub Actions cron (`.github/workflows/daily-digest.yml`) runs it at 01:00 UTC. It writes `docs/YYYY-MM-DD.html`, rebuilds the archive, commits the page and deploys `docs/` to GitHub Pages. A phone push (Bark) arrives when the page is up.

```bash
pip install -r requirements.txt
export GROQ_API_KEY=...   # optional: without it the page has numbers and headlines, no summary
export NEWS_API_KEY=...   # optional
python digest.py          # writes docs/<today>.html and docs/index.html
```

The repo's secrets are `GROQ_API_KEY`, `NEWS_API_KEY` and `BARK_KEY`. None of them are in the code.

## Limits

Yahoo's chart endpoint is unofficial and sometimes returns nothing for a symbol. When it does, the cell shows a dash and the run carries on. The summary is only as good as the day's headlines, so on quiet days it is short.
