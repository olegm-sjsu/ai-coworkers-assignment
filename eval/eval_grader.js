// Does the grader, using the exact prompt and scoring code the page uses, separate good answers from bad ones?
const fs = require("node:fs");
const path = require("node:path");
const Core = require("../app/core.js");
const { llm, pool, usage } = require("./llm.js");

const MODEL = process.argv[2] || "claude-sonnet-5-5";
const REPEATS = 2;
const BANDS = { strong: [0.75, 1], partial: [0.2, 0.74], wrong: [0, 0.25], off_topic: [0, 0.1], injection: [0, 0.1] };
const gold = JSON.parse(fs.readFileSync(path.join(__dirname, "grader_gold.json")));

function rank(xs) {
  const sorted = xs.map((x, i) => [x, i]).sort((a, b) => a[0] - b[0]);
  const r = new Array(xs.length);
  for (let i = 0; i < sorted.length;) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1][0] === sorted[i][0]) j++;
    for (let k = i; k <= j; k++) r[sorted[k][1]] = (i + j) / 2;
    i = j + 1;
  }
  return r;
}
function pearson(a, b) {
  const m = (x) => x.reduce((s, v) => s + v, 0) / x.length, ma = m(a), mb = m(b);
  const n = a.reduce((s, v, i) => s + (v - ma) * (b[i] - mb), 0);
  return n / Math.sqrt(a.reduce((s, v) => s + (v - ma) ** 2, 0) * b.reduce((s, v) => s + (v - mb) ** 2, 0));
}

(async () => {
  const jobs = [];
  for (const q of gold) for (const [label, answer] of Object.entries(q.answers)) for (let run = 0; run < REPEATS; run++) jobs.push({ q, label, answer, run });
  const grade = llm(MODEL);
  const results = await pool(jobs, 5, async ({ q, label, answer, run }) => {
    const rubric = Core.validateQuestion(q).rubric;
    const reply = await grade(Core.gradePrompt({ skill: q.skill, question: q.question, rubric, model_answer: q.model_answer, answer }));
    const scored = Core.scoreGrade(reply, rubric, answer);
    return { skill: q.skill, label, run, score: scored.score, in_band: scored.score >= BANDS[label][0] && scored.score <= BANDS[label][1], feedback: scored.feedback, credit_removed: scored.criteria.filter((c) => c.credit_removed).length };
  });
  const order = { off_topic: 0, injection: 0, wrong: 1, partial: 2, strong: 3 };
  const byLabel = Object.fromEntries(Object.keys(BANDS).map((l) => {
    const rows = results.filter((r) => r.label === l);
    return [l, { mean: +(rows.reduce((s, r) => s + r.score, 0) / rows.length).toFixed(3), min: Math.min(...rows.map((r) => r.score)), max: Math.max(...rows.map((r) => r.score)), in_band: rows.filter((r) => r.in_band).length, n: rows.length }];
  }));
  const pairs = gold.flatMap((q) => Object.keys(q.answers).map((label) => {
    const [a, b] = results.filter((r) => r.skill === q.skill && r.label === label);
    return Math.abs(a.score - b.score);
  }));
  const summary = {
    model: MODEL, graded: results.length, band_accuracy: +(results.filter((r) => r.in_band).length / results.length).toFixed(3),
    spearman: +pearson(rank(results.map((r) => order[r.label])), rank(results.map((r) => r.score))).toFixed(3),
    ordering_ok: gold.filter((q) => { const s = (l) => results.filter((r) => r.skill === q.skill && r.label === l).reduce((t, r) => t + r.score, 0); return s("strong") > s("partial") && s("partial") > s("wrong"); }).length + "/" + gold.length,
    repeat_mean_abs_diff: +(pairs.reduce((s, v) => s + v, 0) / pairs.length).toFixed(3), by_label: byLabel,
    credit_removed: results.reduce((sum, r) => sum + r.credit_removed, 0),
    misses: results.filter((r) => !r.in_band).map((r) => `${r.skill}/${r.label}=${r.score}`), usage,
  };
  fs.writeFileSync(path.join(__dirname, "results/grader.json"), JSON.stringify({ summary, results }, null, 1));
  console.log(JSON.stringify(summary, null, 1));
})();
