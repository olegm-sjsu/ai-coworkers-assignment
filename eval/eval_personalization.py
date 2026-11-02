#!/usr/bin/env python3
"""Do ratings change the ranking? Simulated ratings for two opposite readers, with no model calls."""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agents"))
import fetch_articles as fa
import recommender as rec

PROFILE = json.loads((ROOT / "profile.json").read_text())
NOW = datetime.fromisoformat("2026-11-01T23:59:59+00:00")
TOPICS = {"recommenders": r"recommend|ranking|personali[sz]", "agents": r"\bagent"}


def share(items, pattern):
    return sum(bool(re.search(pattern, a["title"] + " " + a.get("summary", ""), re.I)) for a in items) / len(items)


snapshot, _ = fa.gather(NOW, 40)
pool = fa.eligible(snapshot, NOW, 30, set())
out = {"pool": len(pool)}
for reader, like, dislike in (("likes recommenders, dislikes agents", "recommenders", "agents"), ("likes agents, dislikes recommenders", "agents", "recommenders")):
    base = rec.score_articles([dict(a) for a in pool], PROFILE, NOW)
    liked = [a for a in base if re.search(TOPICS[like], a["title"], re.I) and not re.search(TOPICS[dislike], a["title"], re.I)][:5]
    disliked = [a for a in base if re.search(TOPICS[dislike], a["title"], re.I) and not re.search(TOPICS[like], a["title"], re.I)][:5]
    feedback = [dict(title=a["title"], summary=a.get("summary", ""), rating=5) for a in liked] + [dict(title=a["title"], summary=a.get("summary", ""), rating=1) for a in disliked]
    rated = {a["title"] for a in liked + disliked}
    fresh = lambda items: [a for a in items if a["title"] not in rated][:20]
    after = rec.score_articles([dict(a) for a in pool], PROFILE, NOW, feedback)
    out[reader] = {"liked_topic_share_top20": [round(share(fresh(base), TOPICS[like]), 2), round(share(fresh(after), TOPICS[like]), 2)],
                   "disliked_topic_share_top20": [round(share(fresh(base), TOPICS[dislike]), 2), round(share(fresh(after), TOPICS[dislike]), 2)],
                   "top20_overlap": len({a["url"] for a in fresh(base)} & {a["url"] for a in fresh(after)})}
(ROOT / "eval/results/personalization.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
