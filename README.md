# Economist Digest — POC

An automated weekly briefing tool for central bank economists. Gathers, filters and structures raw economic material — so an economist starts their analysis with sources already organized, not scrolling through feeds and reports.

## The problem

Central bank economists spend a large share of their week gathering material before analysis even starts: central bank communications, economic data releases, financial news. The prep is repetitive and easy to get wrong under time pressure. This is a proof of concept for automating that prep step, while leaving the actual analysis and judgment to the economist.

## What it does not do

The system does not generate policy recommendations, predictions, or the final analytical narrative. It gathers and structures source material with citations; a human decides what it means. See `EVAL.md`, Finding 7, for one place this line gets blurry in the current prompt.

## How it works

```
Fed press feed (RSS)
      │
      ▼
 fetch_real_rss()  ──── parses entries, builds a stable ID per article
      │
      ▼
 Chroma vector store (local, persistent)
      │
      ▼
 collection.query()  ──── retrieves the 5 most relevant chunks
      │
      ▼
 Claude (claude-sonnet-4-5)
      │  system prompt: strict citation format, no fabricated data
      │  tool available: get_fred_indicator
      ▼
 Claude decides to call the FRED tool for FEDFUNDS, CPIAUCSL, UNRATE
      │
      ▼
 Live FRED API  ──── real values returned, stored for later validation
      │
      ▼
 Claude writes the digest, citing sources and FRED values
      │
      ▼
 Automated checks (citation format present, FRED values match)
      │
      ▼
 Human approval gate  ──── nothing saves without a "yes"
      │
      ▼
 reports/weekly_digest_TIMESTAMP.md
```

## Running it

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`) with:
```
ANTHROPIC_API_KEY=your-key-here
FRED_API_KEY=your-key-here
```

Then:
```bash
python3 main.py
```

Without an `ANTHROPIC_API_KEY`, the script runs in a simulated mode using fixed sample text, so the pipeline can still be inspected without live API calls.

## Evaluation

Full findings, root causes and fixes are in [`EVAL.md`](./EVAL.md). Summary:

- A live FRED outage caused the system to correctly disclose the failure instead of inventing a number (Finding 1).
- A citation format gap was found and fixed by tightening the prompt from an example to a strict rule (Finding 2).
- A vector store bug caused the digest to cite old test data even after real data was ingesting correctly — the log was accurate, but retrieval was pulling from stale chunks (Finding 5).
- A related ID bug caused the same article to be stored multiple times across runs (Finding 6).
- Both are fixed and confirmed with repeat runs.

The automated checks are intentionally coarse for v1 (they check that citation tags exist and that FRED numbers appear, not that every claim is individually verified). This is documented as a known limitation, not hidden.

## Known limitations

- Only one live source is wired up (Fed press releases). Reuters and FT were scoped in the original design but dropped after their public RSS feeds could not be verified as live.
- The vector store is wiped on each run, so there's no cross-week comparison yet. That's the natural next increment.
- Fed press releases include routine administrative items (bank approvals, enforcement actions), so a quiet week produces a thin, administrative-sounding digest rather than a monetary-policy-heavy one.

## Next steps

See the "Next steps" section of `EVAL.md` for the prioritized list — freshness checks, retrieval-provenance checks, and resolving the analytical-framing question in Finding 7 are the top three.

## Stack

Python, ChromaDB (local vector store), Anthropic API (Claude Sonnet 4.5, tool use), FRED API, `feedparser`.