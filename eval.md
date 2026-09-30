# Observed guardrail behavior — [18th September]

FRED API failed due to a local SSL certificate issue (unrelated to the AI 
system itself). Rather than fabricating plausible-looking figures, Claude:
- Explicitly disclosed the retrieval failure in the output
- Marked the affected table cells as "Data unavailable" 
- Cited the specific technical reason

The programmatic numeric-exactness check also correctly flagged the missing 
value, and I rejected the report at the HITL checkpoint rather than approving 
an incomplete briefing.

This is a real instance of the "does not fabricate metrics" guardrail from 
the PRD holding under an actual failure, not just a designed test case.


# Citation prompt changed

From :
 "1. Every economic claim or metric MUST end with a precise source citation tag linking back "
"to its specific source chunk or FRED code ID (e.g., [News: news-2026-09-11-reuters-01] or [FRED: CPIAUCSL]).\n"

To: 
"1. Citation format is STRICT: use the exact literal tag [News: <source_id>] for news/speech claims "
"(e.g., [News: news-2026-09-11-reuters-01]) and [FRED: <SERIES_ID>] for data points (e.g., [FRED: CPIAUCSL]). "
"Do NOT use alternate wording such as [Source: ...] — the word 'News' or 'FRED' must appear exactly as shown "
"inside the brackets for every single cited claim.\n"


# Live run findings — [18th September]
## Finding 1: Schema adherence gap (citation tag format)
Claude cited sources using [Source: ...] instead of the instructed [News: ...] 
format. Content was accurate and properly attributed — this was a format 
deviation, not a fabrication. Fixed by making the prompt's citation 
instruction more explicit and example-driven. Classic prompt-iteration/RCA 
pattern: diagnose the specific deviation, don't just "improve the prompt" 
generally.

## Finding 2: Numeric exactness check was validating against stale mock data
The original check hardcoded "5.33" (the old mocked FEDFUNDS value) rather 
than checking against whatever was actually retrieved that run. Fixed by 
capturing real tool-call results into a dict and validating the report 
against those live values instead of a fossilized constant.

## Finding 3: Faithfulness guardrail held under a real failure (earlier run)
When FRED failed due to a local SSL cert issue, Claude did not fabricate 
plausible-looking numbers. It explicitly disclosed the retrieval failure 
and marked affected fields as unavailable. Confirmed the "does not 
fabricate metrics" non-goal holds even under an unplanned real failure, 
not just a designed test case.



Fix verified — [22nd September date]

Applied stricter citation format instruction to system prompt (explicit 
tag format, "Do NOT use alternate wording"). Re-ran live: citation check 
now PASSES consistently. Confirms this was a prompt-specification gap, 
not a model capability gap — Claude followed the strict instruction 
correctly once the ambiguity was removed.


# Live run findings — [22nd September]
## Finding 1: graceful degradation on missing source (local test)

Ran with a feed source that didn't resolve (missing local test file — not
a network failure, but same effect: zero entries returned). The system
correctly detected zero real articles, logged the failure clearly, and
fell back to mock data automatically rather than crashing. Pipeline
completed end to end with the digest still generated and both guardrail
checks still passing on the fallback content.

This is the second distinct failure mode the pipeline has handled
correctly (the first being the FRED SSL outage). Together they show the
fallback/guardrail design holds across different kinds of source failure,
not just one specific scenario.


## Finding 5 — Stale data in the vector store polluted retrieval ✅ (fix confirmed) / ⏳ (digest review pending)
What happened: The log said "Pulled 5 real entries", but the digest cited Reuters and Financial Times articles with the exact titles of my old mock data. My live code only fetches the Fed feed, so those citations could not have come from a live run.
Root cause:
The vector store persists to disk between runs. Mock articles ingested during earlier testing were never removed.
upsert only overwrites chunks with the same ID, so mock and live chunks accumulated together.
My retrieval query included terms from the mock data ("Waller"), so the mock chunks ranked highest and the live chunks were never retrieved.
The log line was true (live items were pulled and stored), but ingestion succeeding did not mean retrieval used them.
How it was found: By reading the citations, not from any check. Listing the store contents showed 16 chunks: 6 mock and 10 live.
Why the checks missed it: The citation check only tests that the tags [News: and [FRED: appear. The numeric check only tests FRED values. Neither tests whether sources are current.
Fix:
Clear existing chunks at the start of each ingestion run.
Replace the tailored query with a generic one.
Add a diagnostic print of the retrieved chunk IDs.
Result: The store held 5 chunks, all live Fed IDs. ⏳ Still to confirm: the digest cites only real recent Fed releases, checked against the live feed.

## Finding 6 — Unstable chunk IDs created duplicates ✅ (fix applied) / ⏳ (second-run check pending)
What happened: The live store held 10 Fed chunks from 5 articles.
Root cause: IDs were built with Python's built-in hash(), which changes every time the program starts. The same article got a new ID each run, so upsert treated it as a new item and the store grew by 5 every run.
Impact: Wasted storage, duplicates competing for the 5 retrieval slots, and the PRD's deduplication was not actually happening.
Fix: Generate the ID from the article link with hashlib.md5, which is the same on every run.
Result: IDs are now short stable hashes. ⏳ Still to confirm: a second run leaves the count at 5.




