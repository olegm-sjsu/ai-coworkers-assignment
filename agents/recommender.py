"""Content-based recommender used by both agents. Standard library only."""
import itertools
import math
import re
from collections import Counter
from datetime import datetime, timezone

STOPWORDS = set("""a about above after again all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her
here hers him his how i if in into is it its just like may me more most my new no nor not now of off on once one only
or other our out over own same she should so some such than that the their them then there these they this those
through to too under until up very was we were what when where which while who whom why will with would you your
via using use used uses make makes made get gets how's it's we're""".split())

# Words that mark corporate news rather than technical depth.
NEWS_TERMS = {"funding", "partnership", "partners", "appoints", "acquires", "acquisition", "customers", "customer",
              "announcing", "announces", "award", "awards", "hiring", "sponsor", "webinar", "summit", "keynote",
              "podcast", "policy", "election", "lawsuit", "pricing", "enterprise-ready", "governance"}
TECH_TERMS = {"architecture", "algorithm", "benchmark", "evaluation", "latency", "training", "inference", "embedding",
              "embeddings", "retrieval", "ranking", "agent", "agents", "orchestration", "pipeline", "framework",
              "implementation", "code", "tool", "tools", "model", "models", "dataset", "memory", "graph", "harness"}

AUTHORITY = {"Anthropic": 1.0, "OpenAI": 1.0, "Google Research": 1.0, "Google": 0.85, "Microsoft Research": 1.0,
             "AWS Machine Learning": 0.85, "LangChain": 0.9, "IBM Research": 0.9, "IEEE Spectrum": 0.9, "ACM Queue": 0.95,
             "arXiv": 0.8, "Hugging Face": 0.85, "Meta Engineering": 0.85, "Netflix Tech Blog": 0.85}


def tokenize(text):
    words = [w for w in re.findall(r"[a-z][a-z0-9+#.-]*[a-z0-9+#]|[a-z]", text.lower()) if w not in STOPWORDS and len(w) > 1]
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


def tfidf_vectors(texts):
    """Return one L2-normalised sparse TF-IDF vector per text, plus the idf table."""
    docs = [Counter(tokenize(t)) for t in texts]
    df = Counter(term for doc in docs for term in doc)
    n = max(len(docs), 1)
    idf = {term: math.log((1 + n) / (1 + count)) + 1 for term, count in df.items()}
    return [normalize({t: (1 + math.log(c)) * idf[t] for t, c in doc.items()}) for doc in docs], idf


def normalize(vec):
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {t: v / norm for t, v in vec.items()} if norm else {}


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def profile_text(profile):
    return " ".join(" ".join([topic] * int(weight)) for topic, weight in profile["interests"].items())


def vectorize_with(idf, text):
    counts = Counter(tokenize(text))
    return normalize({t: (1 + math.log(c)) * idf.get(t, 1.0) for t, c in counts.items()})


def centroid(vectors):
    total = {}
    for vec in vectors:
        for t, v in vec.items():
            total[t] = total.get(t, 0.0) + v
    return normalize(total)


def rocchio(profile_vec, liked, disliked, alpha=1.0, beta=0.8, gamma=0.5):
    """Move the interest vector toward rated-up articles and away from rated-down ones.
    Centroids are normalised so that a few diverse ratings still carry real weight against the profile."""
    out = {t: alpha * v for t, v in profile_vec.items()}
    for vec, weight in ((centroid(liked), beta), (centroid(disliked), -gamma)):
        for t, v in vec.items():
            out[t] = out.get(t, 0.0) + weight * v
    return normalize({t: v for t, v in out.items() if v > 0})


def recency(published, now, half_life_days=7.0):
    age = max((now - published).total_seconds() / 86400, 0.0)
    return 0.5 ** (age / half_life_days)


def depth_signal(text):
    words = Counter(w for w in re.findall(r"[a-z-]+", text.lower()))
    tech = sum(min(words[t], 3) for t in TECH_TERMS)
    news = sum(min(words[t], 3) for t in NEWS_TERMS)
    return max(0.0, min(1.0, 0.5 + 0.08 * tech - 0.2 * news))


def score_articles(articles, profile, now, feedback=None):
    """Attach score parts to each article. Weights: relevance .55, depth .15, authority .15, recency .15."""
    texts = [f"{a['title']} {a['title']} {a['title']} {a.get('summary', '')}" for a in articles]
    vectors, idf = tfidf_vectors(texts)
    user = vectorize_with(idf, profile_text(profile))
    feedback = feedback or []
    liked = [vectorize_with(idf, f"{f['title']} {f.get('summary', '')}") for f in feedback if f.get("rating", 0) >= 4]
    disliked = [vectorize_with(idf, f"{f['title']} {f.get('summary', '')}") for f in feedback if 0 < f.get("rating", 0) <= 2]
    if liked or disliked:
        user = rocchio(user, liked, disliked)
    raw = [cosine(user, v) for v in vectors]
    top = max(raw, default=0.0) or 1.0
    for a, v, r in zip(articles, vectors, raw):
        published = parse_date(a["published"])
        a["relevance"] = round(r / top, 4)
        a["depth"] = round(depth_signal(f"{a['title']} {a.get('summary', '')}"), 4)
        a["authority"] = AUTHORITY.get(a["source"], 0.6)
        a["recency"] = round(recency(published, now), 4)
        a["score"] = round(.55 * a["relevance"] + .15 * a["depth"] + .15 * a["authority"] + .15 * a["recency"], 4)
        matched = sorted(((v[t] * user[t], t) for t in v if t in user), reverse=True)[:5]
        a["matched_terms"] = [t for _, t in matched]
        a["_vec"] = v
    return sorted(articles, key=lambda a: -a["score"])


def session_minutes(picks, cap=5):
    """Reading capped per article, plus one minute per article for the brief's own summary and self-check."""
    return sum(min(a.get("read_minutes", 5), cap) + 1 for a in picks)


def diverse_pool(ranked, size=12, per_source=3):
    """Top of the ranking with a cap per source, so one busy feed cannot fill the shortlist."""
    pool, counts = [], Counter()
    for a in ranked:
        if counts[a["source"]] < per_source:
            pool.append(a)
            counts[a["source"]] += 1
        if len(pool) == size:
            break
    return pool


def select_top3(ranked, budget=(15, 20), pool=12, diversity=0.25, time_penalty=0.15):
    """Best three of a diverse shortlist: distinct sources, low overlap, session time inside the budget."""
    shortlist = diverse_pool(ranked, pool)
    best, best_value = None, -math.inf
    for trio in itertools.combinations(shortlist, 3):
        if len({a["source"] for a in trio}) < 3:
            continue
        overlap = sum(cosine(x["_vec"], y["_vec"]) for x, y in itertools.combinations(trio, 2))
        minutes = session_minutes(trio)
        miss = max(budget[0] - minutes, minutes - budget[1], 0)
        value = sum(a["score"] for a in trio) - diversity * overlap - time_penalty * miss
        if value > best_value:
            best, best_value = trio, value
    return list(best) if best else shortlist[:3]


def parse_date(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
