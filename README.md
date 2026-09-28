# economistdigest
## Product Name
Automated Global Economic Digest

## Problem
Central bank economists produce weekly briefings for policymakers — MPC members, Board of Governors, bank leadership. The briefings are their core deliverable and their reputation rests on the quality of the analysis.
But 30–40% of an economist's week goes to preparation before analysis: gathering central bank communications, tracking economic data releases, reading through financial news, and pre-organizing this material into a usable form. Then, and only then, does the actual analytical work start.
This preparation is repetitive, high-volume, and easy to get wrong under time pressure. Miss an ECB speech, overlook an unexpected CPI print, or skip a Bloomberg story on rate expectations, and the resulting briefing has a blind spot. Blind spots in central bank briefings have consequences.The prep work is the wrong use of the most expensive analytical talent in the building.
## One Paragraph Solution
We're building an automated weekly digest that eliminates the prep, not the analysis. Every Sunday evening, the system pulls the past week's relevant economic material from a curated set of sources — central bank communications, economic indicators, financial news. It filters, deduplicates, cross-references, and structures the material into a Monday-morning digest. The economist opens the digest, sees the week's raw material already organized, and starts analyzing. What used to take 4–6 hours takes 20 minutes of review.

## Data Source
1. RED API (free, easy) — economic indicator
2. RSS feeds (free) — Reuters, FT (partial), central bank RSS
3. BeautifulSoup or feedparser — for RSS parsing
