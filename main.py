import os
import sys
import datetime
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions
import anthropic
import feedparser
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. INITIALIZATION & CONFIGURATION
# ==========================================
ANT_KEY = os.getenv("ANTHROPIC_API_KEY")
FRED_KEY = os.getenv("FRED_API_KEY")

if not ANT_KEY:
    print("⚠️ Warning: ANTHROPIC_API_KEY environment variable is not set.")
    print("Proceeding in Simulation/Mocks mode if keys are unavailable...")

claude_client = None
if ANT_KEY:
    claude_client = anthropic.Anthropic(api_key=ANT_KEY)
else:
    print("ℹ️ Claude API client will run in simulated mode (mocking Sonnet responses).")

chroma_client = chromadb.PersistentClient(path="./chroma_db")
default_ef = embedding_functions.DefaultEmbeddingFunction()
collection = chroma_client.get_or_create_collection(
    name="weekly_economic_data",
    embedding_function=default_ef
)

# Track real values retrieved during this run, for accurate validation later
RETRIEVED_FRED_VALUES = {}

# ==========================================
# 2. INGESTION — REAL RSS + FALLBACK MOCK
# ==========================================
def fetch_real_rss(feed_url: str, source_name: str, max_entries: int = 5) -> list:
    """
    Pulls real entries from a live RSS feed. Returns a list of article dicts
    in the shape the rest of the pipeline expects. If the feed fails
    (network error, feed down, malformed XML) it returns an empty list and
    logs why, rather than crashing the whole pipeline on one bad source.
    This failure-logging IS the PRD's 'Source Completeness Rate' guardrail
    in action — a real source outage should be visible, not silent.
    """
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            print(f"⚠️ Warning: {source_name} feed may be malformed (bozo flag set): {feed.bozo_exception}")

        for entry in feed.entries[:max_entries]:
            published = entry.get('published', entry.get('updated', 'unknown-date'))
            summary = entry.get('summary', entry.get('title', ''))
            link = entry.get('link', entry.get('id', 'no-link'))

            articles.append({
                "id": f"news-{source_name.lower().replace(' ', '-')}-{abs(hash(link)) % 100000}",
                "title": entry.get('title', 'Untitled'),
                "source": source_name,
                "date": published,
                "paragraphs": [summary]
            })
        print(f"✅ Pulled {len(articles)} real entries from {source_name}")
    except Exception as e:
        print(f"❌ Failed to fetch {source_name} feed: {e}")
    return articles


def _get_mock_articles():
    """Fallback mock data — used only if all live RSS feeds fail."""
    return [
        {
            "id": "news-2026-09-11-reuters-01",
            "title": "Fed officials hint at sticky services inflation",
            "source": "Reuters",
            "date": "2026-09-11",
            "paragraphs": [
                "Several Federal Reserve policymakers signaled that core service inflation remains sticky, suggesting rates may stay higher for longer.",
                "Market participants are resetting expectations, now pricing in a November rate hike instead of a pause."
            ]
        },
        {
            "id": "news-2026-09-14-ecb-02",
            "title": "ECB Governing Council divided on next policy move",
            "source": "Financial Times",
            "date": "2026-09-14",
            "paragraphs": [
                "European Central Bank policymakers are emerging divided over whether to raise the deposit rate to a record high of 4.00% or pause.",
                "Stagnant growth across Germany and France has intensified fears of a stagflationary spiral."
            ]
        },
        {
            "id": "cb-2026-09-15-fed-speech",
            "title": "Governor Waller Speech on Economic Outlook",
            "source": "Federal Reserve Board",
            "date": "2026-09-15",
            "paragraphs": [
                "Governor Waller stated that recent labor market cooling is welcoming, but inflation is still too far from the 2% target.",
                "We need to see several more months of cooling before concluding we are done raising rates, Waller noted."
            ]
        }
    ]


def ingest_rss_data(use_local_test_feed: bool = False):
    """
    use_local_test_feed=True points at the local sample_feed.xml instead of
    a live URL — this is ONLY for sandbox/offline testing of the parsing
    logic. On your laptop, run with the default False to hit real feeds.
    """
    if use_local_test_feed:
        feed_sources = [("sample_feed.xml", "Federal Reserve Board (LOCAL TEST FILE)")]
    else:
        # Verify these URLs still resolve in your browser before relying on
        # them — RSS feed availability changes over time.
        feed_sources = [
            ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve Board"),
        ]

    real_articles = []
    for url, name in feed_sources:
        real_articles.extend(fetch_real_rss(url, name))

    if real_articles:
        articles_to_ingest = real_articles
        print(f"📥 Using {len(real_articles)} live articles from real feeds.")
    else:
        print("⚠️ No live articles retrieved — falling back to mock data so the pipeline can still run.")
        articles_to_ingest = _get_mock_articles()

    print("📥 Ingesting into Chroma DB...")
    for art in articles_to_ingest:
        for idx, paragraph in enumerate(art["paragraphs"]):
            chunk_text = f"Source: {art['source']} | Date: {art['date']} | Title: {art['title']} | Content: {paragraph}"
            doc_id = f"{art['id']}_chunk_{idx}"

            collection.upsert(
                documents=[chunk_text],
                ids=[doc_id],
                metadatas=[{
                    "source": art["source"],
                    "date": art["date"],
                    "article_id": art["id"],
                    "type": "news_cb"
                }]
            )
    print("✅ Ingestion & Context-Window Chunking completed successfully.")

# ==========================================
# 3. AGENTIC TOOL DEFINITION (FRED LOOKUP)
# ==========================================
def tool_get_fred_indicator(series_id: str) -> str:
    print(f"📡 Querying FRED series: {series_id}...")

    if FRED_KEY and FRED_KEY != "MOCK_KEY":
        try:
            from fredapi import Fred
            fred_client = Fred(api_key=FRED_KEY)
            data = fred_client.get_series(series_id)
            latest_date = data.index[-1].strftime('%Y-%m-%d')
            latest_value = data.iloc[-1]
            RETRIEVED_FRED_VALUES[series_id.upper()] = str(latest_value)
            return f"FRED Series {series_id}: Last updated {latest_date}, Value: {latest_value}"
        except Exception as e:
            return f"Error pulling from FRED for {series_id}: {str(e)}"
    else:
        mocks = {
            "FEDFUNDS": {"date": "2026-09-01", "value": 5.33, "desc": "Effective Federal Funds Rate"},
            "CPIAUCSL": {"date": "2026-08-31", "value": 314.82, "desc": "Consumer Price Index"},
            "UNRATE": {"date": "2026-09-01", "value": 4.1, "desc": "Civilian Unemployment Rate"}
        }
        series_id_upper = series_id.upper()
        if series_id_upper in mocks:
            m = mocks[series_id_upper]
            RETRIEVED_FRED_VALUES[series_id_upper] = str(m['value'])
            return f"FRED Series {series_id_upper} ({m['desc']}): Last updated {m['date']}, Value: {m['value']}"
        return f"FRED Series {series_id_upper}: (Mock Mode) Returning latest default value: 3.25"

FRED_TOOL_SCHEMA = {
    "name": "get_fred_indicator",
    "description": "Fetch the most recent numeric value and release date for a given FRED series ID.",
    "input_schema": {
        "type": "object",
        "properties": {"series_id": {"type": "string", "description": "FRED Series ID (e.g., FEDFUNDS, CPIAUCSL, UNRATE)."}},
        "required": ["series_id"]
    }
}

# ==========================================
# 4. MULTI-STEP AGENTIC SYNTHESIS (CLAUDE)
# ==========================================
def run_agentic_pipeline() -> str:
    print("🔍 Fetching vector contexts from Chroma DB...")
    query_results = collection.query(
        query_texts=["Federal Reserve ECB policy rates inflation Waller outlook"],
        n_results=5
    )
    retrieved_context = "No database context found."
    if query_results and 'documents' in query_results and query_results['documents']:
        retrieved_context = "\n\n".join(query_results['documents'][0])

    system_prompt = (
        "You are a Senior Central Bank Economist producing a weekly briefing for central bank policymakers.\n\n"
        "Draft a clean, academic, highly analytical markdown weekly briefing.\n\n"
        "CRITICAL COMPLIANCE RULES:\n"
        "1. Citation format is STRICT: use the exact literal tag [News: <source_id>] for news/speech claims "
        "(e.g., [News: news-2026-09-11-reuters-01]) and [FRED: <SERIES_ID>] for data points (e.g., [FRED: CPIAUCSL]). "
        "Do NOT use alternate wording such as [Source: ...] — the word 'News' or 'FRED' must appear exactly as shown "
        "inside the brackets for every single cited claim.\n"
        "2. Do NOT inject personal advice, trading recommendations, rate forecasts, or political opinions.\n"
        "3. You MUST check: FEDFUNDS, CPIAUCSL, UNRATE via 'get_fred_indicator' before drafting.\n"
        "4. Report must contain: # Weekly Global Economic Digest, ## 1. Central Bank Communications Policy Tracker, "
        "## 2. Key Macroeconomic Indicators (table), ## 3. Source Citations Index"
    )

    messages = [{"role": "user", "content": f"Generate the briefing using this context:\n\n{retrieved_context}"}]

    if not claude_client:
        print("🤖 Running simulated Claude processing loop...")
        tool_get_fred_indicator("FEDFUNDS")
        tool_get_fred_indicator("CPIAUCSL")
        tool_get_fred_indicator("UNRATE")
        return "# Weekly Global Economic Digest (Simulated Draft)\n\n[News: news-2026-09-11-reuters-01] [FRED: FEDFUNDS] [FRED: CPIAUCSL] [FRED: UNRATE]\n\nFEDFUNDS: 5.33, CPIAUCSL: 314.82, UNRATE: 4.1"

    print("🤖 Initiating live Claude processing loop...")
    response = claude_client.messages.create(
        model="claude-sonnet-4-5", max_tokens=4000, system=system_prompt,
        tools=[FRED_TOOL_SCHEMA], messages=messages
    )

    while response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results_block = []
        for content_block in response.content:
            if content_block.type == "tool_use":
                print(f"🛠️ Tool execution triggered: {content_block.name}(series_id='{content_block.input['series_id']}')")
                tool_result_text = tool_get_fred_indicator(content_block.input["series_id"])
                tool_results_block.append({
                    "type": "tool_result", "tool_use_id": content_block.id, "content": tool_result_text
                })
        messages.append({"role": "user", "content": tool_results_block})
        response = claude_client.messages.create(
            model="claude-sonnet-4-5", max_tokens=4000, system=system_prompt,
            tools=[FRED_TOOL_SCHEMA], messages=messages
        )
    return response.content[0].text

# ==========================================
# 5. HUMAN-IN-THE-LOOP CHECKPOINT (HITL)
# ==========================================
def save_and_verify_report(report_text: str):
    print("\n🛑 === HUMAN-IN-THE-LOOP CHECKPOINT ===")
    print(report_text)
    print("\n🤖 Running automatic programmatic checks...")
    citation_check = all(c in report_text for c in ["[News:", "[FRED:"])
    print(f"✔️ Programmatic Citation Check: {'PASSED' if citation_check else 'FAILED'}")

    if RETRIEVED_FRED_VALUES:
        for series_id, value in RETRIEVED_FRED_VALUES.items():
            status = "PASSED" if value in report_text else "NOT FOUND"
            print(f"   {'✔️' if status=='PASSED' else '⚠️'} {series_id} = {value}: {status}")

    user_approval = "yes"
    if sys.stdin.isatty():
        user_approval = input("\nApprove saving? (yes/no): ").strip().lower()

    if user_approval in ['yes', 'y']:
        os.makedirs("reports", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"reports/weekly_digest_{timestamp}.md", "w") as f:
            f.write(report_text)
        print(f"💾 Saved.")

if __name__ == "__main__":
    print("🎬 Starting Pipeline...\n")
    # Change to False once you're ready to test against a real live URL on your own machine
    ingest_rss_data(use_local_test_feed=False)
    digest_report = run_agentic_pipeline()
    save_and_verify_report(digest_report)