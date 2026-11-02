#!/usr/bin/env python3
"""Check a brief against the assignment's rules and against the live pages. Exits non-zero on any failure."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import web

REQUIRED = ["title", "source", "published", "url", "summary", "insights", "career_fit", "check_question", "check_answer", "focus", "session_minutes"]
AUTHORITATIVE = {"Anthropic", "OpenAI", "Google", "Google Research", "AWS Machine Learning", "Microsoft Research", "LangChain", "IBM Research",
                 "IEEE Spectrum", "ACM", "arXiv", "Hugging Face", "Meta Engineering", "Netflix Tech Blog"}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def structural_errors(brief):
    errors = []
    articles = brief.get("articles", [])
    if len(articles) != 3:
        errors.append(f"expected 3 articles, found {len(articles)}")
    if len({a.get("url") for a in articles}) != len(articles):
        errors.append("duplicate URL")
    if len({a.get("source") for a in articles}) != len(articles):
        errors.append("duplicate source")
    for a in articles:
        label = a.get("title", "?")[:40]
        errors += [f"{label}: missing {f}" for f in REQUIRED if not a.get(f)]
        if a.get("source") not in AUTHORITATIVE:
            errors.append(f"{label}: source {a.get('source')!r} is not on the authoritative list")
        if len(a.get("insights", [])) < 2:
            errors.append(f"{label}: needs at least 2 insights")
    minutes = sum(a.get("session_minutes", 0) + 1 for a in articles)
    if not 15 <= minutes <= 20:
        errors.append(f"session is {minutes} minutes, outside 15-20")
    if minutes != brief.get("session_minutes"):
        errors.append(f"session_minutes says {brief.get('session_minutes')}, articles add to {minutes}")
    return errors


def page_dates(text):
    """Long-form dates near the top of a page, which is where articles print their own date."""
    found = []
    for month, day, year in re.findall(rf"({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})", text[:1500]):
        found.append(datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date().isoformat())
    return found


def live_errors(brief):
    errors = []
    for a in brief["articles"]:
        label = a["title"][:40]
        text, status = web.article_text(a["url"])
        if status != "ok" or not text:
            errors.append(f"{label}: could not read the page ({status})")
            continue
        head = [w for w in re.findall(r"[a-z0-9]+", a["title"].lower()) if len(w) > 3]
        lowered = text.lower()
        if sum(w in lowered for w in head) < 0.7 * len(head):
            errors.append(f"{label}: the title is not on the page")
        printed = page_dates(text)
        if printed and a["published"] not in printed:
            errors.append(f"{label}: brief says {a['published']}, page prints {printed[0]}")
    return errors


def main():
    brief = json.loads(Path(sys.argv[1]).read_text())
    errors = structural_errors(brief) + ([] if "--offline" in sys.argv else live_errors(brief))
    print(json.dumps({"brief": sys.argv[1], "ok": not errors, "errors": errors, "session_minutes": brief.get("session_minutes")}, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
