// Runs a real model call through `claude -p`, with no tools and no project settings. Used only by the evaluations.
const { spawn } = require("node:child_process");
const os = require("node:os");

const usage = { calls: 0, cost: 0, malformed_replies: 0 };

function parseJson(text) {
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  for (const candidate of [text, fence && fence[1], text.slice(text.search(/[{[]/), Math.max(text.lastIndexOf("}"), text.lastIndexOf("]")) + 1)]) {
    try { if (candidate) return JSON.parse(candidate); } catch (e) { /* try the next form */ }
  }
  throw new Error("No JSON in reply: " + text.slice(0, 200));
}

function raw(prompt, model = "claude-sonnet-5-5") {
  return new Promise((resolve, reject) => {
    const child = spawn("claude", ["-p", "--model", model, "--output-format", "json", "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"], { cwd: os.tmpdir() });
    let out = "", err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", () => {
      try {
        const reply = JSON.parse(out);
        usage.calls++; usage.cost += reply.total_cost_usd || 0;
        if (reply.is_error) return reject(new Error(reply.result));
        resolve(reply.result);
      } catch (e) { reject(new Error("claude -p failed: " + (err || out).slice(0, 300))); }
    });
    child.stdin.end(prompt);
  });
}

// Same shape as sample.json in the page. The page shows "Try again" on a malformed reply, and this retries the same way.
const llm = (model) => async (prompt) => {
  for (let attempt = 0; ; attempt++) {
    const text = await raw(prompt, model);
    try { return parseJson(text); } catch (e) {
      usage.malformed_replies++;
      if (attempt === 3) throw e;
    }
  }
};

async function pool(items, size, fn) {
  const results = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: size }, async () => {
    while (next < items.length) { const i = next++; results[i] = await fn(items[i], i); }
  }));
  return results;
}

module.exports = { llm, raw, parseJson, pool, usage };
