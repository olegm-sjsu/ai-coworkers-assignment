# Simulated session: week1_weak

Learner: simulated persona "weak". This is not a real person's work.

Readiness at start: 35/100

## 1. aws (concept, foundational)

**Coach:** You're deploying a small agent backend on AWS that calls an LLM API, stores user session data, and must read an API key. Explain how IAM roles (attached to the compute, e.g. a Lambda function or EC2 instance) differ from embedding long-lived access keys in the code or environment, and why the principle of least privilege matters here. Then describe one tradeoff between running this backend on AWS Lambda versus a long-running container/EC2 instance for an agent that may take several minutes per request.

**Learner:** I think IAR roles are kind of like keys that AWS hands to your Lambda or EC2 automatically, so you don't have to hardcode a password, and least privilege means giving the app just enough access so it doesn't break. For the tradeoff, Lambda is cheaper and easier to set up, but I think it has a time limit so a multi-minute agent might get cut off, while a container or EC2 box can just keep running.

**Grade:** 45/100. You correctly captured that roles supply credentials automatically so nothing is hardcoded, that least privilege means limited access, and that Lambda's time limit can cut off long agent runs. Missing: that role credentials are temporary and rotated via STS (versus long-lived keys that leak and need manual rotation), that least privilege limits blast radius by scoping to specific actions and resources, the 15-minute figure and cold starts, the idle-cost/ops burden of EC2, and where the API key should live (Secrets Manager or SSM Parameter Store).

**Coach follow-up:** Suppose an attacker exploits a bug in your agent code and runs commands with the role's credentials. How would the policy you wrote determine how bad that is, and what would a well-scoped policy for this backend look like?

**Learner:** It's, like, if someone hacks the agent and uses its login stuff, the policy would kinda decide how much they can mess with. I think you'd want to give it only the permissions it actually needs, like read-only where possible, and maybe limit which commands or tables it can touch, but I'm not totally sure about the specifics.

**Grade:** 18/100. You correctly sense that the policy limits what an attacker can do and that least privilege (only needed permissions, read-only where possible) is the right principle. However, the answer stays vague: it names no actions or resource ARNs, and it never mentions that role credentials are temporary STS tokens or that the API key lives in Secrets Manager/SSM. It also confuses 'commands' with IAM actions, since policies restrict API actions on resources, not shell commands.

Item score: 34/100

## 2. data structures and algorithms (coding, foundational)

**Coach:** Coding: You are matching tasks to contributors. Write a Python function `top_k(scores, k)` that takes a dict mapping contributor_id to a quality score (float) and returns the ids of the k highest-scoring contributors, best first. Example: top_k({'a': 0.7, 'b': 0.9, 'c': 0.4, 'd': 0.8}, 2) should return ['b', 'd']. Then state the time complexity of your approach in terms of n (number of contributors) and k, and explain in one or two sentences when you would choose a heap over sorting the whole dict (for instance with 100,000 contributors and k=10, versus k close to n).

**Learner:** I'd just do `return sorted(scores, key=scores.get, reverse=True)[:k]`, which gives `['b', 'd']` for the example. It's O(n) time since it only loops through the dict once, and I think heaps are better when k is close to n because you don't have to sort everything. Honestly I'm not totally sure about the heap part, but it seemed right.

**Grade:** 40/100. The function is correct and returns ['b', 'd'] in best-first order. However, the complexity is wrong: a full sort is O(n log n), not O(n). The heap reasoning is reversed, since heaps help when k is much smaller than n, not when k is close to n. The answer also omits the O(k) memory point and edge cases such as k > n or ties.

**Coach follow-up:** Your sorted() call has to order all n contributors. With 100,000 contributors and k=10, how would a size-k min-heap avoid that work, and what would the time complexity be?

**Learner:** Um, so you'd keep a heap of just 10 items instead of sorting all 100,000, and you'd like, um, pop the smallest one each time or something? I think it's O(n log n) still, because heaps are kind of like sorting, maybe.

**Grade:** 20/100. You correctly identified the core idea of keeping a heap of only 10 items and popping the smallest, though you were tentative and didn't explain when the pop happens or that the heap stays capped at k. You concluded O(n log n), which is wrong: the heap's size is k, so each operation costs O(log k) and the total is O(n log k). Memory use of O(k) and the fact that the benefit fades as k approaches n were not mentioned.

Item score: 32/100

## 3. typescript (scenario, foundational)

**Coach:** Scenario: You're the first engineer at a two-person startup building an agent that calls an LLM and returns structured JSON (e.g. {"action": "refund" | "escalate", "amount": number}) to a React frontend. A teammate proposes writing the backend in TypeScript, but says: 'Since we declared a TypeScript interface for the LLM's response, we're type-safe and don't need any runtime validation.' Another teammate would rather stay in plain JavaScript to move faster. Decide what you would do and give your reasons. In your answer, explain what TypeScript's types do and do not guarantee at runtime, and say how you would handle the LLM's output.

**Learner:** I'd probably go with plain JavaScript since it's faster and we're only two people, and the TypeScript interface should mean the LLM's JSON gets checked against it automatically. The types get compiled away, so I don't think they matter much at runtime, but if the model follows the format it should be fine. If it sends something weird, I'd just add an if statement or two to catch it.

**Grade:** 35/100. You correctly noted that types are compiled away, and you proposed some manual checks for odd output. But the answer contradicts itself: it says the interface should mean the JSON gets checked automatically, which is exactly the misconception, since erased types check nothing. It also lacks a schema-based validation plan, any handling of failures (retry, escalate, reject), and concrete reasons for the language choice, such as shared types with the React frontend, or details like literal unions and the risk of `as` and `any`.

**Coach follow-up:** You said a couple of if statements would catch weird output. The model returns {"action": "refund", "amount": "50"} and your code does amount * 1.1 before issuing the refund. What happens, and how would your checks and your language choice help or fail to help here?

**Learner:** Um, I think it would just multiply and come out to like 55, so the refund goes out a bit higher, which is bad I guess. My if statements check if the amount is a number, so they'd probably catch it and stop, though I'm not totally sure how they'd do that. Python is pretty forgiving with types, so I think it converts the string automatically, which is why I picked it.

**Grade:** 20/100. You correctly sensed that the wrong refund could go out silently, but you didn't identify the root cause: the amount arrives as a string, and coercion produces a bad value without raising an error. You were unsure how your if statements would catch this, and you didn't explain that types are erased at runtime, so a typeof check or a zod schema is needed. You also didn't say what to do on failure, such as retrying the model or escalating to a human. The language reasoning is muddled: the question is about TypeScript, where a string times a number coerces to a number, and Python would actually raise a TypeError on a string times a float.

Item score: 29/100

## 4. python (concept, intermediate)

**Coach:** In Python, an agent framework runs many LLM calls concurrently. Explain how `asyncio` achieves concurrency with a single thread, and why a single blocking call (such as `time.sleep(5)` or a synchronous `requests.get`) inside an `async def` handler hurts every other in-flight request. Then explain the tradeoff between using `asyncio`, a `ThreadPoolExecutor`, and `multiprocessing` for (a) 200 concurrent LLM API calls and (b) CPU-heavy embedding or feature computation, referring to the GIL in your answer.

**Learner:** asyncio kind of switches between tasks whenever one is waiting on something, so it's basically one thread juggling a bunch of stuff, and a time.sleep inside an async def would freeze the whole loop. For the 200 API calls I'd probably just use ThreadPoolExecutor since threads are faster than asyncio for that, and for the CPU embedding stuff the GIL is kind of a problem, so maybe multiprocessing or threads, I think they're about the same. Honestly I'd just use threads for both since it's simpler.

**Grade:** 30/100. You correctly noted that asyncio is single-threaded, switches tasks while one waits, and that time.sleep in an async def freezes the loop. However, you didn't explain await/cooperative scheduling or name a fix (asyncio.sleep, httpx, to_thread). Your GIL treatment is missing, and the recommendations are wrong: threads are not faster than asyncio for I/O, and threads don't help CPU-bound Python work, so multiprocessing is needed there.

**Coach follow-up:** You said threads and multiprocessing are about the same for CPU-heavy embedding work. If you ran 8 threads on an 8-core machine computing a pure-Python feature function, what speedup would you expect and why?

**Learner:** I think you'd get close to 8x since it's 8 cores doing the work at the same time, so threads should basically split the job evenly. Python's GIL might slow things down a bit, but I'm not really sure how much.

**Grade:** 0/100. The answer expects near 8x speedup, which is the opposite of what happens for pure-Python CPU-bound code under the GIL. It does mention the GIL, but only as a minor slowdown and with admitted uncertainty, and it never explains that only one thread runs bytecode at a time. It also doesn't name multiprocessing or GIL-releasing libraries as the fix.

Item score: 18/100

## Career Readiness Report

Readiness: 33/100 (Early). Started at 35. Demand tested: 48%.

You are at an Early readiness level with a score of 33 and 48% coverage, slightly below your starting score of 35, with no skills yet at strength level. Your biggest gap is Python (39% mastery against 84% demand), where your session answer showed the GIL misunderstanding, followed by gaps in data structures and algorithms, AWS, and TypeScript.

Strengths: none yet

Gaps: python 39, data structures and algorithms 26, aws 27, typescript 25, distributed systems 20

Plan:
- python: Write a CPU-bound function (e.g. counting primes) and benchmark it with 1, 4, and 8 threads using ThreadPoolExecutor versus ProcessPoolExecutor. Write a short note explaining the GIL result and why multiprocessing or GIL-releasing libraries fix it. https://docs.python.org/3/tutorial/ (within 7 days)
- data structures and algorithms: Solve 'Kth Largest Element in a Stream' and 'Top K Frequent Elements' using a size-k min-heap. For each, write the time complexity as O(n log k) and space as O(k), and note when the benefit fades as k approaches n. https://neetcode.io/roadmap (within 7 days)
- aws: Create an IAM role for a Lambda that can only call secretsmanager:GetSecretValue on one specific secret ARN. Store a dummy API key in Secrets Manager, read it from the function, and note that the role issues temporary STS credentials. https://skillbuilder.aws/ (within 7 days)
- typescript: Build a small refund handler that receives an LLM tool-call JSON with the amount as a string. Validate it with a zod schema, and on failure retry the model once and then escalate to a human. Add tests showing that a bad string is rejected rather than coerced. https://www.typescriptlang.org/docs/handbook/intro.html (within 7 days)

Next milestone: Ship a small, deployed agent project (e.g. a tool-calling support agent with validated inputs, least-privilege AWS access, and a ranked recommendation step) and re-take the assessment aiming for a score of 50 or higher.
