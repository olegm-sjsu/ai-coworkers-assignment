import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))
import fetch_articles
import fetch_opportunities as opp
import recommender as rec
import validate_brief
import web

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
PROFILE = {"interests": {"AI agents orchestration": 3, "recommender systems ranking": 2}, "skills": {"python": 0.6}, "reading_minutes": {"min": 15, "max": 20}}


def article(title, source="Hugging Face", days=1, summary="", minutes=5):
    return {"title": title, "source": source, "url": "https://x/" + title.replace(" ", "-"), "published": f"2026-10-{31 - days:02d}T12:00:00+00:00", "summary": summary, "read_minutes": minutes}


class Ranking(unittest.TestCase):
    def test_relevant_article_outranks_unrelated_one(self):
        ranked = rec.score_articles([article("Quarterly cafeteria menu update"), article("Orchestration patterns for AI agents")], PROFILE, NOW)
        self.assertIn("agents", ranked[0]["title"])

    def test_newer_article_wins_when_all_else_is_equal(self):
        ranked = rec.score_articles([article("AI agents orchestration", days=20), article("AI agents orchestration again", days=1)], PROFILE, NOW)
        self.assertGreater(ranked[0]["recency"], ranked[1]["recency"])

    def test_corporate_news_scores_lower_on_depth(self):
        self.assertLess(rec.depth_signal("Company announces funding partnership with customers"), rec.depth_signal("Benchmark of retrieval latency in an agent architecture"))

    def test_top_three_have_distinct_sources_and_fit_the_budget(self):
        items = [article(f"AI agents paper {i}", source=s, minutes=m) for i, (s, m) in enumerate([("arXiv", 9), ("arXiv", 9), ("arXiv", 9), ("OpenAI", 5), ("LangChain", 6), ("Anthropic", 7), ("Google", 6)])]
        picks = rec.select_top3(rec.score_articles(items, PROFILE, NOW))
        self.assertEqual(len({a["source"] for a in picks}), 3)
        self.assertTrue(15 <= rec.session_minutes(picks) <= 20)

    def test_one_busy_source_cannot_fill_the_shortlist(self):
        items = rec.score_articles([article(f"AI agents paper {i}", source="arXiv") for i in range(9)] + [article("AI agents note", source="OpenAI")], PROFILE, NOW)
        pool = rec.diverse_pool(items, 12, per_source=3)
        self.assertEqual(sum(a["source"] == "arXiv" for a in pool), 3)

    def test_ratings_shift_later_recommendations(self):
        items = [article("Vector databases for retail search", summary="vector database index"), article("Protein folding with diffusion", summary="protein structure diffusion")]
        liked = [{"title": "Protein folding methods", "summary": "protein structure diffusion", "rating": 5}, {"title": "Vector database index", "summary": "vector database", "rating": 1}]
        base = {a["title"]: a["relevance"] for a in rec.score_articles([dict(a) for a in items], PROFILE, NOW)}
        moved = {a["title"]: a["relevance"] for a in rec.score_articles([dict(a) for a in items], PROFILE, NOW, liked)}
        self.assertGreater(moved["Protein folding with diffusion"], base["Protein folding with diffusion"])

    def test_seen_and_future_articles_are_excluded(self):
        keep = fetch_articles.eligible([article("seen"), article("fresh"), dict(article("future"), published="2027-01-01T00:00:00+00:00")], NOW, 30, {"https://x/seen"})
        self.assertEqual([a["title"] for a in keep], ["fresh"])


class Parsing(unittest.TestCase):
    RSS = "<rss><channel><item><title>A &amp; B</title><link>https://x/a</link><pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate><description><![CDATA[<p>Hi</p>]]></description></item></channel></rss>"
    ATOM = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title><link rel="alternate" href="https://x/t"/><published>2026-10-29T00:00:00Z</published><summary>S</summary></entry></feed>'

    def test_rss(self):
        self.assertEqual(web.parse_feed(self.RSS)[0], {"title": "A & B", "url": "https://x/a", "published": "2026-10-26T10:00:00+00:00", "summary": "Hi"})

    def test_atom(self):
        self.assertEqual(web.parse_feed(self.ATOM)[0]["url"], "https://x/t")

    def test_feed_with_bare_ampersand_is_repaired(self):
        self.assertEqual(len(web.parse_feed(self.RSS.replace("A &amp; B", "A & B"))), 1)

    def test_text_extraction_prefers_the_article_and_drops_scripts(self):
        body = " ".join(["word"] * 200)
        text = web.extract_text(f"<nav>menu</nav><article><p>{body}</p><script>bad()</script></article><footer>foot</footer>")
        self.assertNotIn("bad", text)
        self.assertNotIn("menu", text)


class Brief(unittest.TestCase):
    def brief(self):
        return json.loads((web.ROOT / "data/briefs/2026-11-01.json").read_text())

    def test_real_brief_passes(self):
        self.assertEqual(validate_brief.structural_errors(self.brief()), [])

    def test_two_articles_fail(self):
        b = self.brief()
        b["articles"].pop()
        self.assertTrue(any("expected 3" in e for e in validate_brief.structural_errors(b)))

    def test_too_long_a_session_fails(self):
        b = self.brief()
        b["articles"][0]["session_minutes"] = 30
        self.assertTrue(any("outside 15-20" in e for e in validate_brief.structural_errors(b)))

    def test_unknown_source_fails(self):
        b = self.brief()
        b["articles"][0]["source"] = "Some Blog"
        self.assertTrue(any("authoritative" in e for e in validate_brief.structural_errors(b)))

    def test_page_date_is_read_from_the_top_of_the_page(self):
        self.assertEqual(validate_brief.page_dates("Jess Weng October 23, 2026 11min"), ["2026-10-23"])


class Opportunities(unittest.TestCase):
    def test_title_filter(self):
        self.assertTrue(opp.is_early_technical({"title": "Machine Learning Engineer, Intern"}))
        self.assertFalse(opp.is_early_technical({"title": "Senior Machine Learning Engineer"}))
        self.assertFalse(opp.is_early_technical({"title": "Marketing Intern"}))

    def test_location_filter(self):
        self.assertTrue(opp.is_reachable({"title": "ML Intern", "location": "San Francisco, CA"}))
        self.assertFalse(opp.is_reachable({"title": "ML Intern", "location": "London"}))
        self.assertFalse(opp.is_reachable({"title": "PhD ML Intern", "location": "San Francisco, CA"}))

    def test_skill_extraction(self):
        self.assertEqual(opp.skills_in("Python, RAG pipelines, and tool-calling agents"), {"python", "rag", "agents"})

    def test_demand_counts_postings_and_uses_priors(self):
        jobs = [{"company": "c", "title": "t", "url": "u", "text": "Python here.", "skills": ["python"]}, {"company": "c", "title": "t", "url": "u", "text": "Python and SQL.", "skills": ["python", "sql"]}]
        rows = {r["skill"]: r for r in opp.demand(jobs, {"skills": {"python": 0.6}})}
        self.assertEqual(rows["python"]["demand"], 1.0)
        self.assertEqual(rows["sql"]["prior_mastery"], 0.2)
        self.assertTrue(rows["python"]["evidence"][0]["excerpt"])


if __name__ == "__main__":
    unittest.main()
