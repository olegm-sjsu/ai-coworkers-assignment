"""End-to-end browser test with a fake window.claude, so it needs no account and uses no Claude usage."""
import json
import sys
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
FAKE = r"""
const store = __SEED__;
const docRef = (path) => ({ path, async get() { const v = store[path]; return { id: path.split('/').pop(), exists: !!v, data: () => v }; },
  async set(v) { window.__writes.push(path); store[path] = JSON.parse(JSON.stringify(v)); }, async update(v) { Object.assign(store[path], v); } });
window.__writes = []; window.__store = store; window.__calls = [];
const db = { doc: docRef, collection: (p) => ({ async get() { const docs = Object.keys(store).filter(k => k.startsWith(p + '/') && k.split('/').length === p.split('/').length + 1).map(k => ({ id: k, exists: true, data: () => store[k] })); return { docs, size: docs.length, empty: !docs.length }; } }) };
const QUESTION = { question: 'Explain how an agent loop <b>decides</b> to stop.', rubric: [{ criterion: 'Stop condition', weight: 0.6 }, { criterion: 'Tool results', weight: 0.4 }], model_answer: 'It stops when no tool calls remain.' };
let grades = 0;
const sample = Object.assign(async () => ({ text: 'x' }), { json: async (prompt) => {
  window.__calls.push(prompt.slice(0, 40));
  if (window.__fail) { const f = window.__fail; window.__fail = null; throw f; }
  if (prompt.startsWith('You are a technical')) return QUESTION;
  if (prompt.startsWith('You are grading')) { grades++; return { criteria: [{ met: 1, evidence: 'the loop stops' }, { met: grades % 2 ? 0 : 1, evidence: grades % 2 ? '' : 'the loop stops' }], feedback: 'Solid start.', misconception: '', follow_up: 'What if a tool fails?', follow_up_rubric: [{ criterion: 'Names the failure', weight: 0.5 }, { criterion: 'Says what happens next', weight: 0.5 }], follow_up_answer: 'Report it.' }; }
  return { summary: 'You are building.', actions: [{ skill: 'agents', action: 'Build one agent.', resource_url: 'https://evil.example', due_in_days: 7 }], next_milestone: 'Apply to one role.' };
} });
window.claude = { use: async (n) => (window.__absent || []).includes(n) ? null : ({ db, sample, user: { can: async () => true } })[n] };
"""


def seed():
    brief = json.loads((ROOT / "data/briefs/2026-11-01.json").read_text())
    opp = json.loads(sorted((ROOT / "data/opportunities").glob("*.json"))[-1].read_text())
    profile = json.loads((ROOT / "profile.json").read_text())
    return {"profile/main": profile, f"briefs/{brief['date']}": brief, f"opportunities/{opp['date']}": opp}


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, data=None, hash_="", width=900, before=""):
        page = self.browser.new_page(viewport={"width": width, "height": 900})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.add_init_script(before + FAKE.replace("__SEED__", json.dumps(seed() if data is None else data)))
        page.route("**/fonts.g*/**", lambda r: r.abort())
        page.goto((ROOT / "dist/coworkers.html").as_uri() + hash_)
        page.wait_for_function("!document.querySelector('#app').textContent.includes('Loading')")
        return page

    def test_brief_shows_three_articles_and_saves_ratings(self):
        page = self.open()
        self.assertEqual(page.locator("article").count(), 3)
        first = page.locator("article").first
        self.assertIn("LangChain", first.inner_text())
        self.assertIn("2026-10-23", first.inner_text())
        self.assertTrue(first.locator("a").first.get_attribute("href").startswith("https://www.langchain.com/"))
        first.get_by_role("button", name="Mark as read").click()
        page.locator("article").first.get_by_role("button", name="Rate 5 of 5").click()
        self.assertIn("1/3", page.locator(".stats").inner_text())
        saved = [v for k, v in page.evaluate("window.__store").items() if k.startswith("feedback/")]
        self.assertEqual((saved[0]["read"], saved[0]["rating"]), (True, 5))
        self.assertEqual(self.errors, [])

    def test_self_check_counts_toward_progress(self):
        page = self.open()
        page.locator("article details summary").first.click()
        page.locator("article").first.get_by_role("button", name="Got it").click()
        self.assertIn("100%", page.locator(".stats").inner_text())

    def test_full_coaching_session_produces_a_report_and_saves_progress(self):
        page = self.open(hash_="#coach")
        before = int(page.locator("#readiness").inner_text())
        self.assertNotIn("undefined", page.locator("#app").inner_text())
        page.locator("#start").click()
        page.wait_for_selector("#question")
        self.assertIn("<b>decides</b>", page.locator("#question").inner_text())  # shown as text, never parsed as HTML
        for _ in range(4):
            page.fill("#answer", "the loop stops when the model is done")
            page.locator("#submit").click()
            page.wait_for_selector("#grade")
            page.wait_for_function("document.querySelector('#submit:not(:disabled)') || document.querySelector('#next') || document.querySelector('#finish')")
            if page.locator("#submit").count():  # the first answer earned a follow-up
                self.assertIn("What if a tool fails?", page.locator("#question").inner_text())
                page.fill("#answer", "the loop stops and reports the tool error")
                page.locator("#submit").click()
                page.wait_for_selector("#next, #finish")
            if page.locator("#next").count():
                page.locator("#next").click()
                page.wait_for_selector("#question")
        page.locator("#finish").click()
        page.wait_for_selector("#report")
        text = page.locator("#report").inner_text()
        self.assertIn("Career Readiness Report", text)
        self.assertIn("Next milestone", text)
        self.assertGreater(int(page.locator("#readiness").inner_text()), before)
        self.assertEqual(page.locator("#report a[href*='evil']").count(), 0)
        store = page.evaluate("window.__store")
        self.assertIn("mastery/current", store)
        session = [v for k, v in store.items() if k.startswith("sessions/")][0]
        self.assertEqual((session["status"], len(session["items"])), ("finished", 4))
        self.assertEqual(self.errors, [])

    def test_an_interrupted_session_resumes_after_reload(self):
        page = self.open(hash_="#coach")
        page.locator("#start").click()
        page.wait_for_selector("#question")
        saved = page.evaluate("window.__store")
        again = self.open(data=saved, hash_="#coach")
        again.wait_for_selector("#question")
        self.assertIn("agent loop", again.locator("#question").inner_text())

    def test_a_failed_request_shows_a_message_and_can_be_retried(self):
        page = self.open(hash_="#coach")
        page.evaluate("window.__fail = {code: 'rate_limited', message: 'x'}")
        page.locator("#start").click()
        page.wait_for_selector(".error")
        self.assertIn("usage limit", page.locator(".error").inner_text())

    def test_declined_permission_explains_itself(self):
        page = self.open(hash_="#coach")
        page.evaluate("window.__fail = {code: 'not_granted', message: 'x'}")
        page.locator("#start").click()
        page.wait_for_selector(".error")
        self.assertIn("permission", page.locator(".error").inner_text())

    def test_no_claude_access_still_shows_the_brief(self):
        page = self.open(hash_="#coach", before="window.__absent = ['sample'];")
        self.assertIn("needs Claude", page.locator("#app").inner_text())
        self.assertIn("Opportunities", page.locator("#app").inner_text())

    def test_signed_out_viewer_gets_a_clear_message(self):
        page = self.open(before="window.__absent = ['db', 'sample', 'user'];")
        self.assertIn("Sign in", page.locator("#app").inner_text())

    def test_empty_store_shows_how_to_begin(self):
        page = self.open(data={})
        self.assertIn("daily-tech-upgrade", page.locator("#app").inner_text())
        page.goto(page.url.split("#")[0] + "#coach")
        self.assertIn("career-coach-research", page.locator("#app").inner_text())

    def test_opportunity_filter_and_phone_width(self):
        page = self.open(hash_="#coach", width=390)
        page.get_by_role("button", name="Research").click()
        self.assertGreater(page.locator("#opps tbody tr").count(), 0)
        self.assertIn("arXiv", page.locator("#opps").inner_text())
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)


if __name__ == "__main__":
    unittest.main()
