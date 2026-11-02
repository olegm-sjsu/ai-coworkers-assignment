# Simulated session: week5_improved

Learner: simulated persona "improving". This is not a real person's work.

Readiness at start: 33/100

## 1. python (concept, foundational)

**Coach:** Python concept: A teammate writes an agent helper `def add_message(msg, history=[]): history.append(msg); return history` and is surprised that separate conversations start seeing each other's messages. Explain the mechanism in Python that causes this (when default arguments are evaluated and what is shared), show the idiomatic fix, and explain one tradeoff or related situation where the same mutable-aliasing behavior bites you, such as passing a list or dict into a function that mutates it, or copying a nested structure with a shallow versus deep copy.

**Learner:** So the default `[]` is a single list object created once when `def` runs, and every call that doesn't pass `history` gets that same object, which is why conversations leak into each other. The idiomatic fix is a `None` sentinel: `def add_message(msg, history=None): history = [] if history is None else history; history.append(msg); return history`. I'd still watch for the same aliasing when a caller passes in their own list, since the function mutates it in place, so I'd copy it with `list(history)` if the caller shouldn't see changes. Nested structures are trickier: `list(history)` is only a shallow copy, so the inner dicts are still shared, and `copy.deepcopy` is needed if the agent edits those.

**Grade:** 90/100. Correct and concise on the definition-time evaluation, the None-sentinel fix, and both the caller-mutation and shallow-vs-deep copy aliasing cases. Missing is any explicit tradeoff or nuance, such as deepcopy's time and memory cost, None being unable to distinguish 'not passed' from an intentional None, or immutable defaults being safe. The fix also doesn't explicitly say why a fresh list per call results, though it is implied.

Item score: 90/100

## 2. data structures and algorithms (coding, foundational)

**Coach:** Scenario: You run a small startup whose agent product dedupes incoming support tickets before sending them to an LLM. Each night a job receives a list of about 2 million ticket IDs (strings), and you must drop duplicates while keeping the first occurrence order, and also check, for each of 50,000 'blocked' IDs, whether it appears in the batch. A teammate wrote the dedupe as `for t in tickets: if t not in seen_list: seen_list.append(t)` and uses `blocked_id in tickets` (a list) for the checks. The job takes hours. Decide what you would change and why. In your answer: (1) name the data structure(s) you would use and explain the mechanism that makes the lookup fast (what hashing does and the average vs worst-case cost), (2) give the before and after time complexity in terms of n, and (3) state one tradeoff or caveat of your choice (e.g. memory, ordering, or hashability), and how you would handle it. Include a short Python snippet (under 10 lines) for order-preserving dedupe.

**Learner:** The `in` checks on a list are the bottleneck. Each one scans the whole list, so the dedupe is O(n²) over 2 million IDs, and each of the 50,000 blocked lookups is O(n). I'd use a `set` for membership: it hashes the string, jumps to a bucket, and compares, so each lookup is O(1) on average (O(n) worst case if many keys collide, which Python's randomized hashing makes rare). That brings dedupe to O(n) and the blocked checks to O(n + m), where m is the 50,000 blocked IDs. A plain set drops insertion order, so I'd use `dict.fromkeys`, which keeps first-seen order in Python 3.7+. The caveat is memory: a dict or set of 2 million strings lives in RAM, so I'd check whether the batch fits or process it in chunks.

```python
def dedupe(tickets):
    return list(dict.fromkeys(tickets))  # O(n), keeps first occurrence order

unique = dedupe(tickets)
batch = set(unique)
hits = [b for b in blocked_ids if b in batch]  # O(1) average per check
```

**Grade:** 100/100. Strong answer: it explains hashing to a bucket, gives average vs worst-case cost, states correct before/after complexities, and provides a correct order-preserving snippet. The memory caveat is valid, though the chunking remedy is vague (chunked dedupe needs a shared seen set to stay correct across chunks) and hashability is not mentioned.

Item score: 100/100

## 3. distributed systems (scenario, foundational)

**Coach:** Scenario: You're the first engineer at a small startup whose agent product processes customer refund requests. Each request triggers a worker that (1) calls an LLM, (2) issues a refund through a payment API, and (3) sends a confirmation email. Requests arrive via a queue (at-least-once delivery), and workers sometimes crash or time out mid-task, after which the queue redelivers the message. In testing, a few customers were refunded twice and emailed twice. A teammate suggests 'just add retries with a short timeout so nothing gets dropped' and another suggests 'make the queue exactly-once.' Decide what you would do and why. In your answer: (1) explain why a timeout or crash leaves you unable to know whether the refund happened, (2) explain what idempotency is and how you would implement it here (e.g., an idempotency key per request, and where it is stored/checked), and (3) state one tradeoff of your approach (e.g., latency, extra storage, at-least-once vs at-most-once, or retry behavior such as backoff).

**Learner:** Retrying with a short timeout won't fix this, because if the payment call times out, we can't tell whether the refund went through, so a retry could refund twice. I'd give each refund request a stable idempotency key, probably the refund request ID, and send it as the `Idempotency-Key` header on the payment API call, which makes the provider return the original result instead of issuing a second refund. I'd also record the key in our own database with a unique constraint and check it before calling the LLM or the payment API, so redelivered messages skip work that's already done. The tradeoff is an extra write and lookup per request and a retention policy for keys. I'd still need to make sure the confirmation email is keyed the same way, since I'm not sure a crash between the refund and the email send would be handled by the same check.

**Grade:** 78/100. Strong on the mechanism: a stable key sent to the payment provider plus a database unique constraint checked before side effects, and valid tradeoffs (storage, lookup, key retention, email idempotency). Missing: an explicit response to the 'make the queue exactly-once' suggestion, a clear statement that you keep at-least-once delivery with idempotent consumers, any mention of backoff, and a definition of idempotency itself. The explanation of why a crash leaves the outcome unknown is brief and does not mention lost responses or redelivery.

**Coach follow-up:** Your worker crashes right after the payment API returns success but before you record the key as completed in your database. The message is redelivered. Walk through exactly what happens, and explain why your design does or does not double-refund and double-email.

**Learner:** I'm pretty sure the fix is an idempotency key, so before the worker calls the payment API I'd write the key to the database with a status of "pending." Then when the message is redelivered, the worker sees the key and skips the refund, so the customer doesn't get charged back twice. The one gap I'd still need to think through is what happens if the worker crashes between the API call and the email send, since the key might already show as "completed" while the email never went out. I'd probably also want to use something like the Outbox pattern so the email is queued in the same transaction as the status update. I haven't fully worked out how the "pending" state gets cleaned up if the worker dies and never comes back, though.

**Grade:** 30/100. You correctly identified that the email is a separate side effect and that a crash between steps is a gap, and writing a pending row before the call is the right instinct. However, your design skips the refund whenever a pending key exists. In the scenario in the question, the crash happened after the payment succeeded but before completion was recorded, so the row is still pending and you cannot know whether the refund happened. The answer never says the worker re-calls the payment API with the same Idempotency-Key so the provider returns the original result. The unique constraint for atomic insertion and the per-step state or email dedupe are also not stated explicitly, and the outbox idea is only partly applicable, since it does not cover a crash between send and record.

Item score: 59/100

## 4. aws (concept, foundational)

**Coach:** Concept: Your agent stores user uploads (PDFs it later embeds) in Amazon S3, and a web app lets users download their own files. Explain two things. (1) How S3 differs from a block disk or filesystem such as EBS attached to an EC2 instance: what is the storage model (objects, keys, buckets), what consistency and durability can you rely on, and why does that make S3 a good fit for uploads but a poor fit for something like a database's data files or frequent small in-place edits? (2) Explain how you would let a user download only their own file without making the bucket public, using pre-signed URLs, and describe the tradeoff of choosing a short versus long expiry time.

**Learner:** S3 is object storage, so you upload a whole blob under a key in a bucket, and you can't edit bytes in place; you overwrite the entire object. That's fine for PDFs you upload once and read later, but it's a bad fit for database data files or small frequent edits, where EBS's block-level access is what you want. S3 now gives strong read-after-write consistency and very high durability across availability zones, so the embedding pipeline can rely on what it reads back. For downloads, I'd keep the bucket private, check in the app that the requesting user owns the object's key, then call `generate_presigned_url` with the GET method so they get a time-limited signed link. A short expiry limits damage if someone copies the link, but a long one is more convenient for slow downloads, so I'd probably pick around 5 minutes. I think that covers it, though the URL is probably only valid as long as the credentials that signed it.

**Grade:** 65/100. Strong on the object-versus-block distinction and on the ownership check before signing a GET URL. Missing: higher per-request latency as a reason against databases, the point that signing uses a limited-permission IAM role so users need no AWS credentials, and that a leaked long-lived URL cannot be easily revoked. The closing remark that the URL is valid only as long as the signing credentials is a hedge that is partly true (temporary role credentials can cut a URL's life short) but it is left vague and undeveloped.

**Coach follow-up:** A user shares their 5-minute download link in a chat, and you later learn the link was leaked within that window. Can you revoke it, and what would you change in your design to limit exposure for sensitive files?

**Learner:** Yes, I'd revoke it by deleting the link's record from the database or Redis so the server rejects it, because the signature alone can't be revoked. For sensitive files, I'd change the design to use a short TTL, a single-use nonce that gets marked as consumed on first use, and an ACL check on every request instead of trusting the signed URL. I'd also keep the bucket private and serve through a signed-URL endpoint so the storage path never leaks. I think I'd miss that a CDN may have already cached the object, so revoking the token doesn't stop an edge copy from being served, and I'd probably forget to purge it.

**Grade:** 15/100. The answer says 'the signature alone can't be revoked', which hints at the right idea, but it opens with 'Yes' and proposes revoking via a database or Redis record. That only works if every download is proxied through your server, which is not how a plain S3 pre-signed URL behaves. Short TTLs and keeping the bucket private are good mitigations. It never mentions deleting or moving the object, revoking the signing role's permissions or session, or that temporary role credentials cap the URL's lifetime.

Item score: 45/100

## Career Readiness Report

Readiness: 41/100 (Building). Started at 33. Demand tested: 56%.

Your readiness score is 41 with 56% coverage, which puts you at the Building level and up from 33 (Early, 48% coverage) when you started. Python (mastery 0.56 against demand 0.84) is your biggest gap, and AWS (0.33 vs 0.52) and TypeScript (0.245 vs 0.48) trail behind, though your data structures answer was strong.

Strengths: none yet

Gaps: python 56, typescript 25, aws 33, rest apis 50, data structures and algorithms 51

Plan:
- python: Build a small agent-style script that calls an LLM API with a tool function, using None-sentinel defaults and deepcopy where needed. Write a short note on the tradeoffs: deepcopy cost, and None versus 'not passed'. https://docs.python.org/3/tutorial/ (within 7 days)
- aws: Create a private S3 bucket and generate pre-signed URLs from both an IAM user and an assumed role. Test how each URL is invalidated by deleting the object, revoking the role's permissions, and letting the temporary credentials expire. Write down what each does. https://skillbuilder.aws/ (within 7 days)
- typescript: Write a typed client for one REST endpoint, with interfaces for the request and response and a discriminated union for success and error results. Make it compile under strict mode. https://www.typescriptlang.org/docs/handbook/intro.html (within 7 days)
- rest apis: Build a FastAPI payment-style endpoint that accepts an Idempotency-Key header, enforces it with a unique DB constraint, and returns the stored result on retry. Test a simulated crash between the charge and recording completion. https://fastapi.tiangolo.com/tutorial/ (within 7 days)

Next milestone: Ship a small public portfolio project, such as an agent with a recommender component deployed on AWS behind a REST API, and then retake the assessment aiming for a readiness score of 55 or higher before you start applying to applied AI engineering roles.
