# Simulated session: control_strong

Learner: simulated persona "strong". This is not a real person's work.

Readiness at start: 35/100

## 1. aws (concept, foundational)

**Coach:** You are deploying a small LLM agent backend on AWS. It needs to call S3 to read user documents and call a hosted model API. A teammate suggests putting an IAM user's access key in the app's environment variables; another suggests attaching an IAM role to the compute (e.g., an EC2 instance or Lambda function). Explain how each approach works mechanistically, which you would choose and why, and what the tradeoff is in terms of security and operations. Also explain how you would scope the permissions for the S3 access.

**Learner:** An IAM user access key is a long-lived static secret placed in environment variables, so anyone who can read the process environment, the task definition, or a leaked log can use it until someone rotates it, and rotation is easy to neglect. An attached IAM role instead makes EC2's instance metadata service (IMDSv2) or Lambda's execution environment vend short-lived STS credentials, which the AWS SDK's default credential chain refreshes automatically, so no secret lives in the app's config. I'd choose the role every time, enforce IMDSv2 with a hop limit of 1 so containers can't reach the metadata endpoint unexpectedly, and reserve static keys for workloads outside AWS, where I'd use federated short-lived tokens instead. The tradeoff is that roles take more upfront wiring (trust policy, instance profile, IMDS settings) and make local development slightly harder, which we solve with SSO profiles that assume the same role. For S3, I'd scope the policy to the exact bucket and prefix the agent needs, such as `arn:aws:s3:::docs-bucket/tenants/*`, allow only `s3:GetObject` and `s3:ListBucket` (the latter restricted with an `s3:prefix` condition), and add an explicit deny for writes and deletes. If the agent serves multiple users, I'd derive the object prefix from the authenticated identity in server code rather than letting model output choose the path, so a prompt injection can't cross tenant boundaries.

**Grade:** 93/100. Strong, accurate answer covering credential mechanics, role choice with security reasoning, and tight least-privilege S3 scoping, plus extras like IMDSv2 hop limit and tenant prefix derivation. The main gap is that it never addresses where the hosted model API key should live (Secrets Manager or Parameter Store), which is a required part of the caveat. It also doesn't explicitly mention limited blast radius from short expiry, though that is implied.

Item score: 93/100

## 2. data structures and algorithms (coding, foundational)

**Coach:** Coding: You run a task-matching service that pairs contributors with tasks. You receive a list of (contributor_id, score) tuples as a stream-like list, and need the top k contributors by score. Write a Python function top_k(pairs, k) in under 25 lines that returns the ids of the k highest-scoring contributors, highest first. Use a heap rather than sorting the whole list, and state the time complexity in terms of n and k. Example: top_k([('a', 0.7), ('b', 0.9), ('c', 0.4), ('d', 0.8)], 2) should return ['b', 'd'].

**Learner:** ```python
import heapq

def top_k(pairs, k):
    if k <= 0:
        return []
    heap = []  # min-heap of (score, index, id); index breaks score ties so ids are never compared
    for i, (cid, score) in enumerate(pairs):
        if len(heap) < k:
            heapq.heappush(heap, (score, i, cid))
        elif score > heap[0][0]:
            heapq.heapreplace(heap, (score, i, cid))
    ordered = sorted(heap, key=lambda t: (-t[0], t[1]))  # highest score first, earlier input first on ties
    return [cid for _, _, cid in ordered]
```

**Complexity:** Time is O(n log k), since each of the n pairs does at most one O(log k) heap operation, and the final sort of k items adds O(k log k), which is dominated by the main loop when k ≤ n. Extra space is O(k). When k is close to n, sorting the whole list is just as good in practice, so I'd only use this when k is small relative to n or when the input is streamed and can't be held in memory.

**Grade:** 90/100. The solution is correct and idiomatic: a size-k min-heap with heapreplace, an index tiebreaker so ids are never compared, and a clear tie rule. Complexity is stated correctly with a sound derivation. The one gap is that it never explicitly says why O(n log k) beats O(n log n) sorting; it only notes when the heap is worthwhile.

Item score: 90/100

## 3. typescript (scenario, foundational)

**Coach:** Scenario: You're the first engineer at a startup building an LLM agent product. Your Node backend calls a model API that returns JSON describing a tool call, e.g. {"tool": "search", "args": {"query": "shoes"}}. A cofounder has written the handler in TypeScript like this: `const call = (await res.json()) as ToolCall;` and then dispatches on `call.tool`. In production, the model occasionally returns malformed output (missing `args`, or an unknown tool name) and the server crashes with 'Cannot read properties of undefined', even though the code compiles with no type errors. Explain why TypeScript did not catch this, and decide what you would change. Name the specific approach you'd use and give the reason for it, including one tradeoff of your approach.

**Learner:** TypeScript never checked this data. `res.json()` returns `Promise<any>`, and the `as ToolCall` cast only tells the compiler to trust the shape, which erases at runtime, so a missing `args` or an unknown `tool` name type-checks cleanly and fails when `call.args.query` is read. I would validate at the boundary where untrusted model output enters the system, using Zod with a discriminated union on `tool`, so each tool's `args` schema is enforced and `z.infer` derives the static types from the same schemas. The dispatcher then receives only parsed, narrowed values, and the `default` branch becomes unreachable by construction. On failure, I would return a structured error to the model for one retry, then fall back to a safe response, and I would log the raw payload. The tradeoff is added per-call latency and a dependency, plus the need to keep schemas in sync with each tool's real implementation; for a hot path I might use generated JSON Schema or a provider's native structured-output mode to constrain generation upstream, but I would still validate on the server because the model can still violate the schema.

**Grade:** 100/100. The answer correctly explains that TypeScript types are erased and that `as ToolCall` asserts rather than verifies. It recommends Zod with a discriminated union, types inferred via `z.infer`, structured-error retry and logging, and names a fitting tradeoff. A small gap is that it never says to type the parsed input as `unknown` explicitly, and it does not say that the erasure means types do not exist at runtime in so many words, though it implies both.

Item score: 100/100

## 4. python (concept, intermediate)

**Coach:** In Python, an agent framework runs many tool calls concurrently. Explain the mechanism behind how `asyncio` achieves concurrency for I/O-bound calls (e.g., many parallel LLM API requests) on a single thread, and why the same approach does not speed up a CPU-bound step such as scoring 1M candidate items in a recommender. For each case (I/O-bound vs CPU-bound), name the Python tool you would reach for and give the main tradeoff of that choice. Include what happens if you accidentally call a blocking function like `time.sleep` or `requests.get` inside an `async def`.

**Learner:** asyncio runs one thread around an event loop that watches sockets through the OS selector (epoll on Linux, kqueue on macOS). Each `await` on a network call suspends its coroutine and registers the socket with the selector, so the loop runs other tasks while the kernel waits on the response, which is why fifty concurrent LLM requests take roughly the latency of one. A CPU-bound step like scoring 1M candidates has no wait to hide, and pure-Python bytecode holds the GIL, so the single thread uses one core no matter how many coroutines you add. For I/O fan-out I'd use `asyncio.TaskGroup` with an `httpx.AsyncClient` and an `asyncio.Semaphore` to cap concurrency; the tradeoff is that every library in the call path must be async-aware, and unbounded fan-out triggers 429s. For CPU-bound scoring I'd use `ProcessPoolExecutor` or NumPy vectorization, since separate processes sidestep the GIL, but you pay for pickling arguments and results across process boundaries and for duplicating data in each worker, so send work in large chunks to amortize that IPC. If you call `time.sleep` or `requests.get` inside an `async def`, the blocking call freezes the entire loop, so every other task stalls and total latency becomes the serial sum instead of the max; the fix is `asyncio.sleep`, an async client, or `await asyncio.to_thread(...)` for legacy blocking code.

**Grade:** 100/100. The answer covers all four rubric points accurately: the selector-based event loop, why CPU-bound work gains nothing, the concrete tools with their tradeoffs, and the loop-freezing effect of blocking calls with fixes. It is precise on details such as chunking to amortize IPC. One gap is that it does not mention that NumPy vectorization often releases the GIL or avoids pickling costs entirely, which would make it the first choice over processes for scoring.

Item score: 100/100

## Career Readiness Report

Readiness: 49/100 (Building). Started at 35. Demand tested: 48%.

Your readiness score rose from 35 (Early) to 49 (Building) with 48% coverage, and Python is your clear strength, backed by 100% graded answers in Python and TypeScript. The biggest remaining gaps are distributed systems (mastery 0.2 vs demand 0.4) and evaluation (0.2 vs 0.32), while REST APIs, DSA and AWS sit close to demand and need only targeted polish.

Strengths: python

Gaps: distributed systems 20, rest apis 50, evaluation 20, data structures and algorithms 55, aws 56

Plan:
- evaluation: Build a small eval harness for a tool-calling agent: write 15 test tasks with graded outcomes, run them, and record pass rate plus the top 3 failure modes in a short write-up. https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents (within 7 days)
- distributed systems: Watch the first two MIT 6.5840 lectures (MapReduce and RPC/threads) and implement the MapReduce lab's coordinator/worker skeleton, noting how it handles worker failure and retries. https://pdos.csail.mit.edu/6.824/ (within 7 days)
- rest apis: Build a FastAPI service with POST and GET endpoints for an agent run, with Pydantic request validation, proper status codes, and idempotency-key handling; and test it with 5 pytest cases. https://fastapi.tiangolo.com/tutorial/ (within 7 days)
- aws: Close the gap from your graded answer: extend your least-privilege S3 design by storing the hosted model API key in Secrets Manager, fetching it via the task role, and writing 3 sentences on how short credential expiry limits blast radius. https://skillbuilder.aws/ (within 7 days)

Next milestone: Publish a portfolio project of a deployed, evaluated agent service (FastAPI on AWS with an eval report), then use it to apply for applied AI engineer roles and as a foundation for a startup prototype.
