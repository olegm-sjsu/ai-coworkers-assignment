#!/usr/bin/env python3
"""Agent 1 tools: gather candidates, rank them for the profile, and pick today's three."""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import recommender as rec
import web

FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google Research": "https://research.google/blog/rss/",
    "Google": "https://blog.google/technology/ai/rss/",
    "AWS Machine Learning": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "Microsoft Research": "https://www.microsoft.com/en-us/research/feed/",
    "LangChain": "https://www.langchain.com/blog/rss.xml",
    "IBM Research": "https://research.ibm.com/rss",
    "IEEE Spectrum": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "Meta Engineering": "https://engineering.fb.com/feed/",
    "Netflix Tech Blog": "https://netflixtechblog.com/feed",
}
ARXIV_API = ("http://export.arxiv.org/api/query?search_query=cat:cs.IR+OR+cat:cs.MA&sortBy=submittedDate"
             "&sortOrder=descending&max_results=40")
ACM_CROSSREF = ("https://api.crossref.org/members/320/works?query.bibliographic=recommender+agents+retrieval"
                "&filter=from-pub-date:{since}&sort=published&order=desc&rows=25&mailto=student@sjsu.edu")
WORDS_PER_MINUTE = 238


def anthropic_articles():
    """Anthropic has no RSS feed, so read the article records embedded in its pages."""
    items = {}
    for page in ("https://www.anthropic.com/engineering", "https://www.anthropic.com/news"):
        markup = web.fetch(page).replace('\\"', '"')
        pattern = (r'"title":"([^"]+)","slug":\{"current":"([a-z0-9-]+)"\},"articleType":"(\w+)",'
                   r'"publishedOn":"(\d{4}-\d{2}-\d{2})"(?:,"linkedUrl":"([^"]+)")?')
        for title, slug, kind, day, linked in re.findall(pattern, markup):
            path = linked or f"/{'research' if kind == 'research' else 'news'}/{slug}"
            items[slug] = {"title": title, "url": "https://www.anthropic.com" + path,
                           "published": day + "T12:00:00+00:00", "summary": ""}
    return list(items.values())


def acm_articles(since):
    data = web.fetch_json(ACM_CROSSREF.format(since=since))
    items = []
    for work in data["message"]["items"]:
        parts = (work.get("published") or {}).get("date-parts", [[]])[0]
        if not work.get("title") or len(parts) < 3:
            continue
        items.append({"title": web.strip_tags(work["title"][0]), "url": work["URL"],
                      "published": "%04d-%02d-%02dT12:00:00+00:00" % tuple(parts[:3]),
                      "summary": web.strip_tags(work.get("abstract", ""))[:2000]})
    return items


def gather(now, window_days):
    since = (now - timedelta(days=window_days)).date().isoformat()
    jobs = {source: (lambda u=url: web.parse_feed(web.fetch(u))) for source, url in FEEDS.items()}
    jobs["Anthropic"] = anthropic_articles
    jobs["arXiv"] = lambda: web.parse_feed(web.fetch(ARXIV_API))
    jobs["ACM (Crossref metadata)"] = lambda: acm_articles(since)
    articles, status = [], {}
    for source, job in jobs.items():
        try:
            items = job()
            status[source] = {"ok": True, "items": len(items)}
        except Exception as exc:  # one dead feed must not stop the brief
            status[source] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
            continue
        for item in items:
            item["source"] = source.replace(" (Crossref metadata)", "")
            articles.append(item)
    return articles, status


def eligible(articles, now, window_days, seen):
    keep, urls = [], set()
    for a in articles:
        published = rec.parse_date(a["published"])
        if a["url"] in seen or a["url"] in urls or published > now or (now - published).days > window_days:
            continue
        urls.add(a["url"])
        keep.append(a)
    return keep


def attach_text(ranked, limit):
    """Read the top of the ranking. Unreadable articles drop out, because they cannot be summarised honestly."""
    readable = []
    for a in ranked[:limit]:
        text, status = web.article_text(a["url"])
        a["fetch_status"] = status
        if len(text.split()) < 150:
            continue
        a["word_count"] = len(text.split())
        a["read_minutes"] = max(1, round(a["word_count"] / WORDS_PER_MINUTE))
        a["text"] = text
        readable.append(a)
    return readable


def load_json(path, default):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def public(article):
    return {k: v for k, v in article.items() if not k.startswith("_")}


def run(date, profile, feedback, seen, articles=None, status=None, window_days=30, read_limit=40):
    now = datetime.fromisoformat(date + "T23:59:59+00:00")
    if articles is None:
        articles, status = gather(now, window_days)
    pool = eligible([dict(a) for a in articles], now, window_days, seen)
    ranked = rec.score_articles(pool, profile, now, feedback)
    readable = attach_text(rec.diverse_pool(ranked, read_limit, per_source=6), read_limit)
    picks = rec.select_top3(readable, (profile["reading_minutes"]["min"], profile["reading_minutes"]["max"]))
    return {"date": date, "feeds": status, "candidates_total": len(articles), "eligible": len(pool),
            "read": len(readable), "session_minutes": rec.session_minutes(picks),
            "selected": [public(a) for a in picks],
            "ranking": [{k: a.get(k) for k in ("title", "source", "published", "url", "score", "relevance", "depth",
                                               "authority", "recency", "matched_terms", "fetch_status")} for a in ranked[:30]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--profile", default=str(web.ROOT / "profile.json"))
    parser.add_argument("--feedback", default=str(web.ROOT / "data" / "feedback.json"))
    parser.add_argument("--seen", default=str(web.ROOT / "data" / "seen.json"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    result = run(args.date, load_json(args.profile, {}), load_json(args.feedback, []), set(load_json(args.seen, [])))
    out = Path(args.out or web.ROOT / "data" / "candidates" / f"{args.date}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({"out": str(out), "feeds_ok": sum(f["ok"] for f in result["feeds"].values()),
                      "feeds_total": len(result["feeds"]), "eligible": result["eligible"], "read": result["read"],
                      "session_minutes": result["session_minutes"],
                      "selected": [[a["source"], a["title"], a["read_minutes"], a["score"]] for a in result["selected"]]}, indent=1))


if __name__ == "__main__":
    main()
