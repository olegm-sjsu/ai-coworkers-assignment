// Runs full coaching sessions end to end with simulated learners. These are synthetic personas, not a real person.
const fs = require("node:fs");
const path = require("node:path");
const Core = require("../app/core.js");
const { llm, raw, usage } = require("./llm.js");

const ROOT = path.join(__dirname, "..");
const opp = JSON.parse(fs.readFileSync(path.join(ROOT, "data/opportunities", fs.readdirSync(path.join(ROOT, "data/opportunities")).sort().at(-1))));
// The persona has its own name, so a simulated report can never be read as a real person's result.
const profile = { ...JSON.parse(fs.readFileSync(path.join(ROOT, "profile.json"))), name: "the simulated learner" };
const coach = llm("claude-sonnet-5-5");
const PERSONAS = {
  weak: "a beginner CS student who has used Python in classes but never built agents or production systems. You give short, vague answers, you often miss key points, and you sometimes state something incorrect with confidence. Do not exceed 3 sentences.",
  improving: "a CS student who spent the past month studying these topics. You get the main idea right and name specific techniques, but you overlook one or two edge cases. Write 3 to 5 sentences, or short code.",
  strong: "an experienced applied AI engineer. You answer precisely, name concrete techniques and tradeoffs, and cover edge cases. Write 4 to 6 sentences, or correct code with a complexity note.",
};
const learner = (persona, prompt) => raw(`You are role-playing ${PERSONAS[persona]}\n\nAnswer this interview question in character. Output only the answer text.\n\n${prompt}`, "claude-haiku-5-5");

async function run(name, persona, stored, history) {
  const log = [`# Simulated session: ${name}`, "", `Learner: simulated persona "${persona}". This is not a real person's work.`, ""];
  const s = Core.createSession({ id: name, profile, demand: opp.demand, storedMastery: stored, size: 4, startedAt: new Date().toISOString() });
  log.push(`Readiness at start: ${s.startReadiness.score}/100`, "");
  while (await Core.nextQuestion(s, coach, history)) {
    const q = s.current;
    log.push(`## ${s.items.length + 1}. ${q.skill} (${q.type}, ${q.difficulty})`, "", `**Coach:** ${q.prompt}`, "");
    for (;;) {
      const answer = await learner(persona, s.current.prompt);
      log.push(`**Learner:** ${answer}`, "");
      const r = await Core.submitAnswer(s, answer, coach);
      log.push(`**Grade:** ${Math.round(r.score * 100)}/100. ${r.feedback}`, "");
      if (!r.follow_up_next) break;
      log.push(`**Coach follow-up:** ${s.current.prompt}`, "");
    }
    log.push(`Item score: ${Math.round(s.items.at(-1).score * 100)}/100`, "");
  }
  const report = await Core.finishSession(s, coach, opp.resources, new Date().toISOString());
  log.push("## Career Readiness Report", "", `Readiness: ${report.readiness.score}/100 (${report.readiness.level}). Started at ${report.start_readiness.score}. Demand tested: ${report.readiness.coverage}%.`, "", report.summary, "",
    `Strengths: ${report.strengths.join(", ") || "none yet"}`, "", "Gaps: " + report.gaps.map((g) => `${g.skill} ${Math.round(g.mastery * 100)}`).join(", "), "", "Plan:", ...report.actions.map((a) => `- ${a.skill}: ${a.action} ${a.resource_url} (within ${a.due_in_days} days)`), "", `Next milestone: ${report.next_milestone}`);
  fs.writeFileSync(path.join(ROOT, "samples", `coaching_${name}.md`), log.join("\n") + "\n");
  fs.writeFileSync(path.join(__dirname, "results", `session_${name}.json`), JSON.stringify(s, null, 1));
  return s;
}

(async () => {
  const first = await run("week1_weak", "weak", null, []);
  const second = await run("week5_improved", "improving", first.skills, first.items.map((i) => i.question));
  const strong = await run("control_strong", "strong", null, []);
  const scores = (s) => s.items.map((i) => i.score);
  const mean = (x) => +(x.reduce((a, b) => a + b, 0) / x.length).toFixed(3);
  const allActions = [first, second, strong].flatMap((s) => s.report.actions);
  const allowed = new Set(Object.values(opp.resources).flat().map((r) => r.url));
  const summary = {
    sessions: Object.fromEntries([first, second, strong].map((s) => [s.id, { start: s.startReadiness.score, end: s.report.readiness.score, coverage: s.report.readiness.coverage, item_scores: scores(s), mean_item: mean(scores(s)), skills: s.items.map((i) => i.skill), types: s.items.map((i) => i.type), follow_ups: s.items.filter((i) => i.answers.length > 1).length, narrative: s.report.narrative }])),
    distinct_questions: new Set([first, second, strong].flatMap((s) => s.items.map((i) => i.question))).size,
    credit_removed: [first, second, strong].flatMap((s) => s.items.flatMap((i) => i.answers.flatMap((a) => a.criteria))).filter((c) => c.credit_removed).map((c) => c.criterion.slice(0, 80)),
    follow_up_scores: [first, second, strong].flatMap((s) => s.items.filter((i) => i.answers.length > 1).map((i) => [s.id, i.skill, i.answers[0].score, i.answers[1].score])),
    plan_links_valid: allActions.filter((a) => !a.resource_url || allowed.has(a.resource_url)).length + "/" + allActions.length, usage,
  };
  fs.writeFileSync(path.join(__dirname, "results/sessions.json"), JSON.stringify(summary, null, 1));
  console.log(JSON.stringify(summary, null, 1));
})();
