#!/usr/bin/env python3
"""Agent 2 tools: find opportunities, read job descriptions, and measure the skills the market asks for."""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_articles as articles
import recommender as rec
import web

BOARDS = {
    "greenhouse": ["anthropic", "databricks", "scaleai", "figma", "stripe", "cohere", "perplexity", "pinecone", "airbnb", "lyft", "robinhood", "instacart"],
    "ashby": ["openai", "langchain", "cohere", "perplexity", "pinecone", "notion", "replit", "ramp", "cursor"],
    "lever": ["spotify", "mistral", "palantir"],
}
NAMES = {"anthropic": "Anthropic", "databricks": "Databricks", "scaleai": "Scale AI", "figma": "Figma", "stripe": "Stripe", "cohere": "Cohere", "perplexity": "Perplexity",
         "pinecone": "Pinecone", "airbnb": "Airbnb", "lyft": "Lyft", "robinhood": "Robinhood", "instacart": "Instacart", "openai": "OpenAI", "langchain": "LangChain",
         "notion": "Notion", "replit": "Replit", "ramp": "Ramp", "cursor": "Cursor", "spotify": "Spotify", "mistral": "Mistral AI", "palantir": "Palantir"}
EARLY = re.compile(r"\b(intern|internship|new grad|new graduate|university|early career|residen|fellow|apprentice|co-?op|junior|entry)\b", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head of|vp|architect)\b", re.I)
TECHNICAL = re.compile(r"\b(engineer|engineering|scientist|research|developer|machine learning|\bml\b|\bai\b|software)\b", re.I)
SEEDS = [
    {"kind": "entrepreneurship", "title": "SJSU Innovation and SpartUp programs", "org": "San Jose State University", "url": "https://www.sjsu.edu/innovation/",
     "why": "On-campus route to test a startup idea and find mentors."},
    {"kind": "entrepreneurship", "title": "Silicon Valley Innovation Challenge", "org": "San Jose State University", "url": "https://www.sjsu.edu/svic/about-us/index.php",
     "why": "SJSU competition for pitching a venture. An AI coworker product is a natural entry."},
    {"kind": "entrepreneurship", "title": "Y Combinator application", "org": "Y Combinator", "url": "https://www.ycombinator.com/apply",
     "why": "Benchmark for founder readiness, even before you apply."},
]
SKILLS = {
    "python": r"\bpython\b", "sql": r"\bsql\b", "typescript": r"\btypescript\b", "pytorch": r"\bpytorch\b",
    "machine learning": r"\bmachine learning\b|\bml\b", "deep learning": r"\bdeep learning\b|\bneural net",
    "llm": r"\bllms?\b|large language model|generative ai|\bgenai\b", "rag": r"\brag\b|retrieval[- ]augmented",
    "embeddings": r"\bembeddings?\b|vector (search|database|store)", "agents": r"\bagents?\b|agentic|tool[- ]calling|multi-agent",
    "evaluation": r"\bevals?\b|evaluation|benchmark", "recommender systems": r"recommend(er|ation)|ranking|personali[sz]ation",
    "distributed systems": r"distributed systems?|scalab", "system design": r"system design|architecture|design systems",
    "kubernetes": r"\bkubernetes\b|\bk8s\b", "docker": r"\bdocker\b|container", "aws": r"\baws\b|\bgcp\b|\bazure\b|cloud",
    "data structures and algorithms": r"data structures|algorithms", "testing": r"\btesting\b|\bunit tests?\b|\bci/cd\b",
    "rest apis": r"\bapis?\b|\brest\b|backend", "entrepreneurship": r"entrepreneur|founder|startup|0 to 1|zero to one",
}


def greenhouse(company):
    data = web.fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true")
    return [{"company": company, "title": j["title"], "url": j["absolute_url"], "location": (j.get("location") or {}).get("name", ""),
             "published": j.get("updated_at") or j.get("first_published"), "text": web.strip_tags(j.get("content", ""))} for j in data["jobs"]]


def ashby(company):
    data = web.fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{company}")
    return [{"company": company, "title": j["title"], "url": j["jobUrl"], "location": j.get("location", ""),
             "published": j.get("publishedAt"), "text": web.strip_tags(j.get("descriptionHtml", ""))} for j in data["jobs"]]


def lever(company):
    data = web.fetch_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
    return [{"company": company, "title": j["text"], "url": j["hostedUrl"], "location": (j.get("categories") or {}).get("location", ""),
             "published": datetime.utcfromtimestamp(j["createdAt"] / 1000).isoformat() + "+00:00", "text": j.get("descriptionPlain", "") + " " + web.strip_tags(" ".join(l.get("content", "") for l in j.get("lists", [])))} for j in data]


def gather_jobs():
    fetchers = {"greenhouse": greenhouse, "ashby": ashby, "lever": lever}
    jobs, status = [], {}
    for board, companies in BOARDS.items():
        for company in companies:
            key = f"{board}:{company}"
            try:
                found = fetchers[board](company)
                status[key] = {"ok": True, "items": len(found)}
                jobs.extend(found)
            except Exception as exc:  # companies change boards; a miss is expected and reported
                status[key] = {"ok": False, "error": f"{type(exc).__name__}"}
    return jobs, status


def is_early_technical(job):
    title = job["title"]
    return bool(EARLY.search(title)) and not SENIOR.search(title) and bool(TECHNICAL.search(title))


def is_reachable(job):
    """Keep roles this student can plausibly take: US or remote, and not PhD-only."""
    location = job.get("location") or ""
    us = re.search(r"\b(remote|united states|usa|u\.s\.|san francisco|san jose|new york|seattle|palo alto|menlo park|mountain view|sunnyvale|bay area|austin|boston|chicago|[A-Z][a-z]+, (CA|NY|WA|TX|MA|IL))\b", location)
    return bool(us) and "phd" not in job["title"].lower()


def is_junior_friendly(job):
    return not SENIOR.search(job["title"]) and bool(TECHNICAL.search(job["title"]))


def skills_in(text):
    return {skill for skill, pattern in SKILLS.items() if re.search(pattern, text, re.I)}


def excerpt(text, pattern, width=220):
    match = re.search(pattern, text, re.I)
    if not match:
        return ""
    start = max(text.rfind(".", 0, match.start()) + 1, match.start() - width)
    return text[start:match.end() + width].strip()


def rank_jobs(jobs, profile):
    """Same content-based score as the articles: TF-IDF match against interests, plus the skill overlap."""
    if not jobs:
        return []
    vectors, idf = rec.tfidf_vectors([f"{j['title']} {j['title']} {j['text'][:6000]}" for j in jobs])
    user = rec.vectorize_with(idf, rec.profile_text(profile))
    raw = [rec.cosine(user, v) for v in vectors]
    top = max(raw) or 1.0
    known = set(profile["skills"])
    for job, r in zip(jobs, raw):
        needed = skills_in(job["text"] + " " + job["title"])
        job["skills"] = sorted(needed)
        job["missing_skills"] = sorted(needed - known)
        job["fit"] = round(.7 * r / top + .3 * (len(needed & known) / len(needed) if needed else 0), 4)
    return sorted(jobs, key=lambda j: -j["fit"])


def demand(jobs, profile, limit=12):
    """Share of the target postings asking for each skill, and the starting mastery we assume for it."""
    counts = Counter(skill for job in jobs for skill in job["skills"])
    total = max(len(jobs), 1)
    rows = []
    for skill, count in counts.most_common(limit):
        evidence = []
        for job in jobs:
            if skill in job["skills"]:
                quote = excerpt(job["text"], SKILLS[skill])
                if quote:
                    evidence.append({"company": NAMES.get(job["company"], job["company"]), "title": job["title"], "url": job["url"], "excerpt": quote[:420]})
            if len(evidence) == 2:
                break
        rows.append({"skill": skill, "demand": round(count / total, 3), "postings": count,
                     "prior_mastery": profile["skills"].get(skill, 0.2), "evidence": evidence})
    return rows


def verified_resources():
    """Keep only learning links that still answer, so the coach can never cite a dead page."""
    table = json.loads((Path(__file__).parent / "resources.json").read_text())
    good = {}
    for skill, links in table.items():
        for title, url in links:
            try:
                web.fetch(url, timeout=30)
                good.setdefault(skill, []).append({"title": title, "url": url})
            except Exception:
                pass
    return good


def research_items(profile, limit=4):
    items = web.parse_feed(web.fetch(articles.ARXIV_API))
    for item in items:
        item["source"] = "arXiv"
    now = datetime.now().astimezone()
    ranked = rec.score_articles(items, profile, now)[:limit]
    return [{"kind": "research", "title": a["title"], "org": "arXiv", "url": a["url"], "published": a["published"],
             "why": "Recent paper on your interests (" + ", ".join(a["matched_terms"][:3]) + "). Reproducing or extending it is a research-project starting point."} for a in ranked]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    args = parser.parse_args()
    profile = json.loads((web.ROOT / "profile.json").read_text())
    jobs, status = gather_jobs()
    jobs = [j for j in jobs if is_reachable(j)]
    early = [j for j in jobs if is_early_technical(j)]
    target = early if len(early) >= 15 else early + [j for j in jobs if is_junior_friendly(j) and j not in early]
    ranked, unique = rank_jobs(target, profile), set()
    ranked = [j for j in ranked if (j["company"], j["title"]) not in unique and not unique.add((j["company"], j["title"]))]
    top = ranked[:25]
    seeds = []
    for seed in SEEDS:
        try:
            web.fetch(seed["url"], timeout=15)
            seeds.append(seed)
        except Exception as exc:
            status["seed:" + seed["url"]] = {"ok": False, "error": type(exc).__name__}
    opportunities = [{"kind": "internship" if re.search(r"intern", j["title"], re.I) else "job", "title": j["title"], "org": NAMES.get(j["company"], j["company"]), "url": j["url"],
                      "location": j["location"], "published": j["published"], "fit": j["fit"], "skills": j["skills"], "missing_skills": j["missing_skills"],
                      "early_career": is_early_technical(j)} for j in ranked[:12]]
    result = {"date": args.date, "boards": status, "jobs_total": len(jobs), "early_career_total": len(early), "analyzed": len(top),
              "opportunities": opportunities, "research": research_items(profile), "ventures": seeds,
              "demand": demand(top, profile), "resources": verified_resources(), "role_focus": profile["target_roles"][0]}
    out = web.ROOT / "data" / "opportunities" / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({"out": str(out), "jobs_total": result["jobs_total"], "early": result["early_career_total"], "boards_ok": sum(b["ok"] for b in status.values()), "boards": len(status),
                      "top": [[o["kind"], o["org"], o["title"], o["fit"]] for o in opportunities[:8]],
                      "demand": [[d["skill"], d["demand"]] for d in result["demand"]], "resources": {k: len(v) for k, v in result["resources"].items()},
                      "missing_resources": sorted(set(json.loads((Path(__file__).parent / 'resources.json').read_text())) - set(result["resources"]))}, indent=0))


if __name__ == "__main__":
    main()
