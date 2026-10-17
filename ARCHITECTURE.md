# Banyan: how it works today

Banyan is a **multi-agent system with humans as gatekeepers**. A goal goes in; a team of
specialised agents coordinates to answer it; whenever something is new, risky or uncertain,
the human decides. This file explains what exists now (Phases 0-3 built; voice, vault and
Google are not built yet).

## 1. The agent team

| Agent | Job | Tools it may use |
|---|---|---|
| **Planner** (root) | Splits the goal into 2-5 subtasks with dependencies and gives each a role | none |
| **Researcher** | Finds facts on the web | `web_search`, `fetch_url`, `current_time` + approved grown tools |
| **Analyst** | Compares / ranks / calculates from what other agents found (never searches) | `calculate`, `current_time` + grown tools |
| **Writer** | Produces deliverables, sends email | `send_email` (human approval, always), `current_time` |
| **Synthesizer** | The planner merges all subtask results into one answer | none |
| **Builder / Tester / Critic** | The Toolsmith: build, test and security-review a *new* tool | none (sandbox only) |

Each agent has its own prompt (`orchestrator/agents.py`) and only sees the tools for its role,
so a Researcher cannot send email and an Analyst cannot browse.

## 1b. Right-sized teams: parallel when it helps, nothing wasted

- The Planner answers directly when no fresh data is needed (1 node) and uses ONE researcher
  for a single fact. For options, recommendations, comparisons or research it **fans out 2-4
  researchers in parallel** (one per source / store / angle) plus an **analyst** that waits for
  them and ranks the results; independent parts of a goal ("email X *and* find cars") run in
  parallel too. It never adds setup / verify / summarize steps. (Real Gemini, "email … and find
  good cars under 20 lac": writer ∥ 3 researchers → analyst, 6 agents.)
- In the tree, an agent that waits for siblings sits below them with dashed **"feeds"** arrows.
- **Session memory:** every goal in a session sees the last 5 goals and answers, so a follow-up
  like "which of those is best on fuel?" is understood (and answered without new searches).
- **Answers** are Markdown (summary line, sections, ranked tables, source links) and can carry
  **images** from `image_search`. They appear in the **💬 Conversation** panel next to the
  tree, with live progress while agents work and a follow-up box.
- **Honest actions:** if Gmail isn't connected, `send_email` asks you to sign in with Google;
  if it still can't send, the tool says NOT SENT and the answer says so.
- With one subtask there is nothing to merge, so no synthesis call is made.
- Workers must try `web_search` / `fetch_url` / `calculate` before asking for a tool.
- **Tool gate:** when a worker does ask for a tool, a cheap check first decides whether one is truly needed. If existing tools can do it, no Builder/Tester/Critic runs, no approval is requested, and the worker is sent back to use what it has.
- Generated tools can never reuse a built-in name.

## 1c. Sessions and standing agents (watchers)

One **session** (the `?session=` in the URL) is one mission-control screen. Every goal typed
there is a new run in that session, and runs execute **side by side**, each with its own tree.

Some goals don't end: "Any time I get an email related to payment, tell me." The Planner
recognises this (`standing_watch`) and spawns a **Watcher** agent (`app/watchers.py`):

1. The Watcher asks the human for mailbox access with a **credential card**: **Sign in with
   Google** (OAuth in a popup, `api/routes_auth.py` + `connectors/google.py`, scopes
   `gmail.readonly` + `gmail.send`; the refresh token is stored as vault secret `google`),
   an IMAP app password, or the demo inbox. It goes straight into the
   **vault** (`app/vault.py`, Fernet-encrypted with `VAULT_KEY`); the approval, the events
   and the LLM never contain it. Approving without a credential is refused by the API.
2. The Watcher connects with the read-only **email connector** (`connectors/email_inbox.py`:
   IMAP with the mailbox opened read-only and `BODY.PEEK`, or the demo inbox), and remembers
   where the inbox ends, so only *new* mail counts.
3. Its goal's request ends, but the Watcher node stays `watching` (cyan glow).
4. Serverless can't run anything in the background, so the open page calls
   `POST /api/sessions/{id}/tick` every 5 s; each Watcher checks at most once per
   `WATCH_INTERVAL_SEC` (atomic claim, so two tabs never double-check). New mail is judged by
   the LLM against the rule; each match becomes an **alert** card and a 🔔 child node.
   (A cron job could call the same tick endpoint so alerts also arrive with the tab closed.)
5. Pause / resume / prune work on a Watcher like on any agent. Mail that arrives while it
   is paused is caught on resume.

For demos, **📨 Simulate email** drops a payment bill, a receipt, a newsletter or a personal
note into the demo inbox. Only the payment ones should alert.

**Watcher actions.** For each match the Watcher also *proposes* a follow-up: `track_bill` (a
bill still to pay) or `mark_paid` (a receipt). It is a normal approval card; nothing happens
until a human approves. Approving adds the entry to the **📒 Bills tracker** (`bills` table,
`bill_tracked` event) and grows a child node under the alert.

**Alerts with no tab open.** `GET|POST /api/watches/tick_all` wakes every watcher in every
session; it requires `Authorization: Bearer $CRON_SECRET`. Two callers:
- `.github/workflows/watchers.yml`: GitHub Actions every 5 minutes (repo secret `CRON_SECRET`;
  GitHub may delay scheduled runs).
- `backend/vercel.json` cron: once a day (the Vercel Hobby limit), as a fallback.
Alerts found this way are stored as events and appear when the session is opened. To be told
right away, add an **ntfy topic** on the credential card: each alert is pushed to your phone
via ntfy.sh (the topic name is kept in the vault, since it is the only protection on ntfy).
With the tab open in the background, the browser can also show **desktop notifications**.

## 1d. System Map and Timeline

The centre panel switches between three views, all derived from the same event stream:
- **🌳 Agent tree:** the recursive trees, one per goal.
- **🛰️ System map:** the fixed components (You, Orchestrator, Agents, LLM, SerpAPI, Web, Tool
  Registry, Sandbox, Vault, Email inbox, Database, Phone). Each event is mapped to the edge it
  travels (`flowsFor` in `store/useBanyan.ts`) and a particle runs along it; gold particles
  mean a secret was used by a connector. Edge numbers count messages so far.
- **📊 Timeline:** one lane per agent on a shared time axis, coloured by status, with ▲ for
  tool calls and 🔔 for alerts. Overlapping bars show parallelism ("up to N at once").
  Filters: human moments only, last 2 minutes.

## 1e. Voice

- **Talk to it:** click 🎙 (Chrome) and say a goal ("Banyan, compare gold prices in Lahore and
  Karachi") or a command: *approve, reject …, pause, resume, stop, status, explain, show the
  map / timeline / tree, send a payment email*. EN / اردو input. `POST /api/voice/command`
  parses commands with rules (instant, predictable); anything else becomes a new goal.
  Voice uses the same API calls as the buttons and sends no `confirm`, so **a high-risk
  approval still needs a click**.
- **It talks back:** short lines for important moments only (approval needed, critic block,
  tool loaded, alert, task complete), max two queued. Each agent role has its own voice:
  ElevenLabs (`ELEVENLABS_API_KEY`, optional, via `POST /api/voice/speak` with a phrase cache)
  or, without a key, the browser's free `speechSynthesis` with a different pitch per role.

## 1f. Stage demo tools

- **▶ Demo** starts the payment watcher and a 3-store comparison side by side.
- **📋 Script** opens the 4-minute presentation checklist with two extra buttons:
  **🔧 Toolsmith demo** and **☠️ Unsafe build** (`POST /api/debug/toolsmith_demo`). These use
  the scripted model so the Builder → Tester → Critic → human → hot-load loop (and the blocked
  malicious build) happens the same way every time; a real model is rightly reluctant to
  build tools it doesn't need. That tool targets the reserved `goldprice.example.pk`
  domain, and real agents skip tools whose domains are all `*.example.*`.
- **Tool Library** shows each grown tool's lineage: Builder → tests passed → Critic → the
  human who approved it and when, plus connectors that hold vault secrets.
- `tests/e2e_demo.py [base_url]` checks the stage demo; it passes against a real-LLM server.

## 2. How they coordinate

Example: "Compare the price of a MacBook Air at 3 Pakistani stores".

```
Planner  ──► t1 Researcher (Daraz)    ┐
         ──► t2 Researcher (PriceOye) ├─ run IN PARALLEL (asyncio, semaphore = MAX_PARALLEL_AGENTS)
         ──► t3 Researcher (Mega.pk)  ┘
         ──► t4 Analyst  depends_on t1,t2,t3 ─► starts only when all three finish,
                                                 receives their results as context,
                                                 uses `calculate` to find the cheapest
Planner  ──► synthesizes t1..t4 into the final answer
```

- **DAG execution** (`orchestrator/runner.py`): a subtask starts as soon as everything it
  `depends_on` is done; independent ones run concurrently. Dependency results are passed
  forward as context.
- **Recursion:** a worker may answer "this is too big" and the runner plans that sub-goal
  again one level deeper, up to `MAX_DEPTH`. Past the limit it must answer directly.
- **Failure isolation:** a branch that fails or is pruned returns nothing; its siblings and
  the run continue. The planner only fails if *every* subtask failed.
- **Missing capability -> growth:** if a worker says "I have no tool for this" the Toolsmith
  runs (section 4) and the worker retries with the new tool.

## 3. Where the human is in the loop

| Moment | What happens | Who can decide |
|---|---|---|
| New tool built | Approval card: code, spec, tests, critic report | approve or reject |
| Tool blocked by security checks | Card is red; **approve is refused by the API**, only reject | reject |
| Irreversible action (`send_email`) | Branch pauses; high risk needs an explicit UI click (`confirm`) | approve / reject |
| Low confidence (< 0.6) | Branch pauses showing its answer | approve, **edit the answer**, or reject |
| Over token budget (`BRANCH_TOKEN_BUDGET`) | Branch pauses | approve more / reject |
| Any time | Click a node: **pause, resume, prune** (cancels the whole subtree), **redirect** to a new goal, or **add a note** | you |

Only the waiting branch blocks; every other branch keeps running.

## 4. The Toolsmith (growing a new capability)

```
worker: "no tool for gold prices"
  └─► Builder writes the tool (follows the contract in toolsmith/tool_template.py)
       └─► static check: AST allowlist + bandit   (up to 2 automatic fix-ups)
            └─► Tester writes cases; run in the sandbox with NO network (HTTP mocked)
                 └─► Critic reviews code + static report + test output
                      └─► HUMAN approves / rejects
                           └─► saved to the DB = live immediately (hot-load, no restart)
                                └─► worker retries and uses it
```

Safety layers (all tested in `tests/test_toolsmith.py`):
1. **Static check:** only allowlisted imports; no `eval/exec/open/getattr/print`, no private
   or dunder attributes; every URL must be in `allowed_domains`; no hard-coded keys; secrets
   may never reach a return value.
2. **Sandbox:** generated code never runs in the server. Each call is a separate Python
   process (`-I`), empty environment, temp working dir, hard timeout. Network only through
   `ctx.http_get/http_post`, which re-checks the domain at runtime. Secrets are scoped per
   tool and every use is recorded.
3. **Critic + human:** an independent review, then a person decides. Failing its own tests
   also counts as blocked.

Honest limit: this is process isolation + static analysis, not a kernel jail.

## 5. Tools today

Built in (5): `web_search` (SerpAPI), `fetch_url`, `calculate` (safe arithmetic),
`current_time`, `send_email` (always a high-risk click; sends through your Gmail once you
signed in with Google, otherwise a mock that only logs; the card says which; mock/test runs
never send).
Grown: anything the Toolsmith builds and a human approves; shown in the Tool Library with
usage count, domains and a disable button. The header reads
"Started with 5 tools - Humans approved N".

## 6. Architecture (and why it looks like this)

- **Frontend** (Next.js on Vercel): every pixel is derived from an **event stream**
  (`store/useBanyan.ts`). Refreshing replays the run from stored events.
- **Backend** (FastAPI on Vercel, Tokyo region next to the database).
- **Database** (Supabase Postgres): events, agent control state, approvals, tools.
- **Serverless constraints** drive the design: no WebSockets and no background tasks, so
  (a) the browser **polls** `GET /api/runs/{id}/events?after=<seq>`; (b) a goal runs inside
  one long request (`POST /api/goals`, up to `maxDuration`); (c) humans and the running
  orchestrator talk **through the database** (control flags, approvals) instead of memory,
  which also means a decision can arrive on a different server instance.
- **LLM layer** (`orchestrator/agents.py`): OpenAI Agents SDK with three providers, chosen
  automatically: OpenAI (`OPENAI_API_KEY`), else Google Gemini via its OpenAI-compatible
  endpoint (`GEMINI_API_KEY`, default model `gemini-3.5-flash-lite`, free tier), else a
  scripted **mock** (also forced by `MOCK_LLM=1`). Gemini cannot combine tool calling with a
  JSON response schema, so tool-using agents run in two passes (use tools in plain text, then
  a formatter call structures the answer). Rate limits / overload (429, 500, 503) are retried
  with backoff. The mock makes tests deterministic, including a deliberately malicious tool
  (add the word "sneaky" to the gold-price goal).

## 7. Testing

```
cd backend
.venv/Scripts/python -m pytest tests/test_toolsmith.py     # safety layer (10 tests)
MOCK_LLM=1 .venv/Scripts/python -m uvicorn  # e2e suites need mock mode app.main:app --port 8000
.venv/Scripts/python tests/e2e_phase1.py [base_url]        # parallelism, approvals, prune, analyst, email
.venv/Scripts/python tests/e2e_phase3.py [base_url]        # toolsmith + blocked malicious build
.venv/Scripts/python tests/e2e_phase4.py [base_url]        # session, parallel goals, watcher, vault, alerts
                                                            # (also passes on production with real Gemini)
```

## 8. Not built yet

Google Calendar, publishing the Google app (it is in Testing: only listed test users can sign in),
self-repair, explain/replay modes, scheduling (Phase 7). Verified with real Gemini: planning,
parallel researchers with live SerpAPI, analyst, synthesis, and a real Toolsmith build
(Builder retried after failing tests). Free-tier Gemini is slow (a 3-store comparison takes
~2.5 minutes) and can be rate-limited.
