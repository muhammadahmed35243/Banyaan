# BANYAN — Build Plan

> Agents that grow their own tools, with humans as the gatekeepers.
> Like a banyan tree that grows new roots from its branches, Banyan's agents spawn sub-agents and grow new capabilities, and nothing takes root without human approval.
> Hackathon: NASCOM 26 Agentic 2.0 · Theme: **Human in the Loop**

**Instructions for Claude Code:** Read this whole file first. Build **one phase at a time**, in order. After each phase, run the app and check every item in that phase's **Acceptance** list before moving on. Do not skip ahead to voice or visuals before the core loop works. When an API detail here conflicts with the current official docs of a library (FastMCP, OpenAI Agents SDK, ElevenLabs, React Flow), **follow the docs** and leave a short comment explaining the change.

---

## 0. Vision and the finished product

> Read this section to understand **what the end result must feel like**. Every technical decision below serves this picture.

### The vision
Today's AI agents are stuck with the tools a developer gave them. When they hit something they can't do, they fail, or worse, they improvise unsafely. Banyan is an agent system that **grows its own capabilities on demand**, the way a banyan tree grows new roots from its branches, while keeping a human as the **gatekeeper of what the AI is allowed to become**.

The core idea: **humans don't just approve actions, they approve capabilities.** Banyan is a working model of how autonomous AI can expand its abilities safely: every new skill is written, tested, reviewed by an AI critic, and finally approved by a human before it exists.

### The problem it solves
- Agents fail silently or hallucinate when they lack a tool.
- Giving agents unlimited power (run any code, use any credential) is unsafe.
- Approving every tiny step is exhausting, so people stop reading and click "approve" blindly.

Banyan's answer: **let the agent do the work, and pull the human in only at the moments that matter**: new capabilities, secrets, irreversible actions, low confidence, and budget limits. Every such moment comes with clear evidence (code, tests, critic report) so the human can decide in seconds.

### Who it is for
- **Individuals and freelancers** who want an assistant that can learn new jobs (track prices, monitor sites, summarize email) without writing code.
- **Small businesses** that need custom automations but can't afford developers for each one, and need control over what runs with their accounts.
- **Teams and companies** exploring agentic AI who need an audit trail and governance over what their agents can do.

### The finished product: what a user experiences
1. The user opens Banyan in the browser: a dark, cinematic **mission control** screen. A small tree icon sits at the center, the voice orb glows at the top, and the Tool Library says *"5 tools"*.
2. They say, or type: **"Banyan, tell me the gold price in PKR every morning and email it to my team on Fridays."**
3. The **agent tree grows live**. The root splits into branches: find the gold price, format a report, email it on a schedule. Branches run **in parallel**, and their colors change as they think, call tools, and finish. Swimlanes at the bottom show the overlapping work.
4. One branch realizes it has **no tool for gold prices**. A purple **Toolsmith** branch sprouts: Builder writes the code, Tester runs tests, Critic reviews it. The System Map shows data flowing between components.
5. Banyan **speaks**: *"I built a new tool for gold prices. It passed 4 tests. Please review."* An approval card opens with the code, tests, the critic's report, and the domains it will access. The user approves in one click. The tool is **hot-loaded** and used immediately, and the answer appears.
6. The email step needs Gmail. Banyan asks for Google sign-in through a secure flow. The token goes into the **vault**, never into the AI. Because sending email is irreversible, it asks again before sending, and the user must click, not just speak.
7. In another run, the builder produces a tool that tries to send data to an unknown website. The **critic blocks it** and Banyan warns out loud in the critic's voice. The user rejects it, and the agent continues safely without it.
8. At any time the user can click any branch to **pause, prune, or redirect** it, or ask out loud *"why did you do that?"* and watch Banyan highlight its reasoning path on the tree.
9. At the end, the Tool Library reads: **"Started with 5 tools · Humans approved 9."** Every approval, secret use, and decision is in the audit log, and any run can be **replayed**.

### Definition of done (for the hackathon)
The project is complete when a judge can watch, live and in under 5 minutes:
- A goal decomposed into a **recursive, parallel agent tree**, visible in real time
- The agent **building, testing, and critiquing a brand-new tool**, then a human approving it and the agent using it **without a restart**
- A **dangerous tool being caught and rejected**
- **Secrets handled safely** (vault, scopes, audit, revoke), never exposed to the LLM
- **Human control** over any branch (pause, prune, redirect) while other branches keep running
- **Voice** interaction for commands and agent narration
- A polished UI that makes the whole system understandable at a glance

### What Banyan is NOT
- Not a chatbot. The chat-style input is only a way to give goals; the product is the visible, controllable agent system.
- Not fully autonomous. Autonomy is deliberately bounded by human checkpoints.
- Not a code editor. Users review generated tools; they don't need to write any.

### The future beyond the hackathon
- **Earned autonomy:** after a human approves the same kind of action many times, Banyan offers to auto-approve it, and the user can revoke that at any time.
- **Shared tool marketplace:** tools approved by one user (after review) can be shared with a team or community, with ratings and security reports.
- **Organization governance:** roles (who can approve which risk levels), policies, and compliance-ready audit exports.
- **Multi-human loops:** routing approvals to the right person (a manager for payments, an IT admin for new credentials).
- **Local language support:** Urdu and other regional languages for voice, so non-technical users can teach their assistant new skills by speaking.

---

## 1. What we are building

A web app where a user gives a goal (typed or spoken). A **root agent** breaks it into sub-tasks and spawns **sub-agents** recursively, running independent ones **in parallel**. When an agent needs a capability it does not have, it does not fail — it runs the **Toolsmith pipeline**:

1. **Builder** agent writes a new Python tool
2. **Tester** agent writes tests and runs them in a sandbox
3. **Critic** agent reviews the code for security risks (backed by static analysis)
4. **Human** reviews code, test results and the critic report, then approves or rejects
5. On approval the tool is **hot-loaded into the live FastMCP server** and the agent uses it

Everything the agents do is streamed live to a "mission control" UI: an animated **agent tree**, a **system map** with animated data flow, **swimlane logs**, an **approval inbox**, a **tool library**, and a **secrets vault**. The agents can **talk** (ElevenLabs) and accept **voice commands**.

### Human-in-the-loop principles (must be visible in the product)
- **Risk-based checkpoints:** low-risk actions run alone; new tools, secret use, and irreversible actions (send email, write to external services) always pause for a human.
- **Confidence escalation:** every agent result carries a `confidence` (0–1). Below `0.6` → ask a human.
- **Budgets:** each branch has a token/cost budget; exceeding it pauses and asks.
- **Other branches keep running** while one waits for a human.
- **Audit trail:** every decision records who approved what and when.
- **The LLM never sees a secret value.**

---

## 2. Tech stack

### Backend (Python 3.11+)
| Purpose | Library |
|---|---|
| API + WebSocket | FastAPI, Uvicorn |
| Agents | OpenAI Agents SDK (`openai-agents`) |
| Orchestration, recursion, parallelism | plain `asyncio` (TaskGroup, Semaphore) — written by us |
| Tool server | FastMCP (mounted inside the FastAPI app, streamable HTTP) |
| Web search | SerpAPI (`google-search-results`) |
| Google | `google-auth-oauthlib`, `google-api-python-client` (Gmail, Calendar, Drive) |
| Schemas | Pydantic v2 |
| DB | SQLite + SQLModel |
| Secrets encryption | `cryptography` (Fernet) |
| Generated-tool tests | pytest |
| Static security scan | bandit + our own AST checker |
| Recurring tools | APScheduler |
| HTTP for tools | httpx |
| Voice out | `elevenlabs` |
| Package manager | uv (or pip + venv) |

### Frontend
| Purpose | Library |
|---|---|
| App | Next.js (App Router) + TypeScript |
| UI | Tailwind CSS + shadcn/ui, dark theme |
| Graphs | React Flow (`@xyflow/react`) + `dagre` for auto-layout |
| Animation | Framer Motion |
| Code diff | `@monaco-editor/react` |
| State | Zustand |
| Charts | Recharts |
| Voice in | Browser Web Speech API (Chrome) — free |
| Audio out / orb | `<audio>` + Web Audio API analyser |

---

## 3. Repository layout

```
banyan/
├── PLAN.md                      # this file
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              # FastAPI app, mounts MCP, routes, WS
│   │   ├── config.py            # settings from .env
│   │   ├── db.py                # SQLModel engine + tables
│   │   ├── models.py            # Pydantic/SQLModel: Event, Task, Tool, Approval, Secret
│   │   ├── events.py            # EventBus (pub/sub → WebSocket + DB)
│   │   ├── orchestrator/
│   │   │   ├── runner.py        # run_goal(), recursive spawn, DAG execution
│   │   │   ├── budget.py        # token/cost tracking per branch
│   │   │   └── agents.py        # Planner, Worker, Builder, Tester, Critic, Narrator definitions
│   │   ├── approvals.py         # ApprovalService (asyncio.Future per request)
│   │   ├── mcp_server/
│   │   │   ├── server.py        # FastMCP instance + built-in tools
│   │   │   ├── registry.py      # load / hot-load / unload generated tools
│   │   │   └── builtin_tools.py # web_search, gmail_read, calendar_free_slots, ...
│   │   ├── toolsmith/
│   │   │   ├── pipeline.py      # builder → tester → critic → human → load
│   │   │   ├── sandbox.py       # subprocess runner with timeout + restricted env
│   │   │   ├── static_check.py  # AST checker + bandit wrapper
│   │   │   └── tool_template.py # contract every generated tool must follow
│   │   ├── vault/
│   │   │   ├── vault.py         # encrypted secret store, scopes, audit
│   │   │   └── google_oauth.py  # OAuth flow, token storage in vault
│   │   ├── voice/
│   │   │   └── tts.py           # ElevenLabs streaming + phrase cache
│   │   └── api/
│   │       ├── routes_goals.py
│   │       ├── routes_approvals.py
│   │       ├── routes_tools.py
│   │       ├── routes_vault.py
│   │       ├── routes_voice.py
│   │       └── ws.py
│   ├── generated_tools/         # one folder per approved tool (git-ignored)
│   ├── audio_cache/             # pre-generated fixed phrases
│   └── tests/
└── frontend/
    ├── package.json
    └── src/
        ├── app/page.tsx         # mission control
        ├── lib/ws.ts            # WebSocket client, reconnect, replay
        ├── store/useBanyan.ts  # Zustand store fed by events
        └── components/
            ├── AgentTree.tsx
            ├── SystemMap.tsx
            ├── Swimlanes.tsx
            ├── ApprovalInbox.tsx
            ├── ApprovalCard.tsx  # Monaco diff + critic report + tests
            ├── ToolLibrary.tsx
            ├── VaultPanel.tsx
            ├── SecretForm.tsx
            ├── NodeDetails.tsx
            ├── GoalInput.tsx
            └── VoiceOrb.tsx
```

---

## 4. Environment variables (`.env.example`)

```
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini          # cheap default; set a stronger model for Builder/Critic if budget allows
OPENAI_MODEL_STRONG=
SERPAPI_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/oauth/google/callback
ELEVENLABS_API_KEY=
ELEVENLABS_MODEL=eleven_flash_v2_5
VAULT_MASTER_KEY=                  # Fernet key: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
MAX_PARALLEL_AGENTS=5
MAX_DEPTH=3
BRANCH_TOKEN_BUDGET=40000
CONFIDENCE_THRESHOLD=0.6
SANDBOX_TIMEOUT_SEC=20
FRONTEND_ORIGIN=http://localhost:3000
```

Never commit `.env`. Never send any key to the frontend.

---

## 5. Core data models

```python
class Event(BaseModel):
    id: str
    run_id: str
    type: Literal[
        "run_started", "run_finished",
        "agent_spawned", "agent_status", "agent_thought", "agent_finished", "agent_failed",
        "tool_call", "tool_result",
        "needs_human", "human_decision",
        "toolsmith_stage",          # builder | tester | critic | awaiting_review | loaded | rejected
        "tool_loaded", "tool_unloaded",
        "secret_requested", "secret_used",
        "budget_warning", "speak",  # speak → frontend plays TTS
        "system_flow",              # for animating System Map edges: {from, to}
        "log"
    ]
    agent_id: str | None
    parent_id: str | None
    ts: datetime
    payload: dict

class AgentNode:            # in-memory + persisted
    id, run_id, parent_id, depth, role, goal,
    status: Literal["queued","thinking","running_tool","waiting_human","done","failed","paused","pruned"],
    confidence: float | None, tokens_used: int, result: str | None

class Approval:
    id, run_id, agent_id, kind: Literal["new_tool","secret_access","risky_action","low_confidence","budget"],
    title, details: dict, risk: Literal["low","medium","high"],
    status: Literal["pending","approved","rejected","edited"], decided_by, decided_at, note

class ToolRecord:
    name, version, description, input_schema, secrets_required: list[str],
    allowed_domains: list[str], risk_level, status: Literal["pending","active","rejected","disabled"],
    approved_by, approved_at, composed_from: list[str], usage_count, code_path

class SecretRecord:
    name, ciphertext, allowed_tools: list[str], allowed_domains: list[str],
    permission: Literal["read","write"], expires_at, created_at
```

---

## 6. Backend components

### 6.1 EventBus (`events.py`)
- `async publish(event)` → append to SQLite and push to every WebSocket subscriber of that `run_id`.
- WebSocket `/ws/{run_id}`: on connect, send all past events for that run (enables refresh + **replay mode**), then stream new ones.
- Every other module talks to the UI **only** through events.

### 6.2 Orchestrator (`orchestrator/runner.py`)
- `run_goal(goal) -> run_id`: creates the root node, starts it as a background task.
- **Planner agent** returns structured output:
  ```json
  {"subtasks":[{"id":"t1","goal":"...","depends_on":[],"needs_capability":"optional text"}],
   "direct_answer": null}
  ```
  If the goal is simple, `direct_answer` is set and no children are spawned.
- **DAG execution:** run all subtasks whose dependencies are done, concurrently, using `asyncio.TaskGroup` gated by a global `asyncio.Semaphore(MAX_PARALLEL_AGENTS)`. Pass finished dependency results into dependent tasks.
- **Recursion:** a Worker may return `{"needs_decomposition": true}` → the runner calls the Planner on that sub-goal with `depth+1`. At `MAX_DEPTH`, decomposition is refused and the worker must solve directly or escalate to a human.
- **Missing capability:** if a Worker reports `{"missing_tool": {"name_hint","description","example_input"}}`, the runner calls `toolsmith.pipeline.build_tool(...)` and, once loaded, retries the worker.
- **Confidence:** Workers return `confidence`. Below threshold → `ApprovalService.request(kind="low_confidence")` showing the answer; the human can accept, edit, or redirect.
- **Budget:** `budget.py` tracks tokens per branch (from Agents SDK usage). Over budget → approval of kind `budget`.
- **Human controls (from UI or voice):** `pause(agent_id)`, `resume`, `prune` (cancel the subtree), `redirect(agent_id, new_goal)`, `inject(agent_id, note)`. Implement with a per-node control flag checked between steps plus task cancellation for prune.
- Emit `agent_spawned`, `agent_status`, `agent_thought` (short summaries, not chain-of-thought dumps), `tool_call`, `tool_result`, `agent_finished`, and `system_flow` events throughout.

### 6.3 Agents (`orchestrator/agents.py`)
Define each with the OpenAI Agents SDK, structured outputs via Pydantic.

| Agent | Job | Output |
|---|---|---|
| Planner | Decompose a goal into a small DAG (2–5 subtasks) | `PlanOutput` |
| Worker | Solve one subtask using MCP tools | `WorkerOutput {result, confidence, missing_tool?, needs_decomposition?}` |
| Builder | Write a tool that follows `tool_template.py` | `BuiltTool {name, code, spec}` |
| Tester | Write pytest tests for the tool (mock network with `respx` or fixtures) | `TestFile {code}` |
| Critic | Review code + static-check report; list risks with line numbers | `CriticReport {verdict: pass|warn|block, issues:[{line, severity, message}]}` |
| Narrator | Turn events into a short spoken line (≤ 12 words) | `{text, voice_role}` |

Workers connect to our FastMCP server as an MCP client (streamable HTTP). **Disable tool-list caching** so newly loaded tools appear on the next call.

### 6.4 ApprovalService (`approvals.py`)
- `async request(kind, title, details, risk) -> Decision`: stores an `Approval`, publishes `needs_human`, creates an `asyncio.Future`, awaits it. Only the waiting branch blocks.
- `POST /api/approvals/{id}/decide {decision, note, edited_payload?}` resolves the future and publishes `human_decision`.
- `risk == "high"` requires `confirm: true` from a UI click — a voice "approve" alone is **not** enough for high risk.

### 6.5 FastMCP server (`mcp_server/`)
- Create the FastMCP instance and mount its HTTP app inside FastAPI (e.g. at `/mcp`).
- **Built-in tools** (start with these 3–5):
  - `web_search(query)` — SerpAPI, returns top results (title, link, snippet)
  - `fetch_url(url)` — httpx GET, returns cleaned text (truncated)
  - `gmail_search(query)` — read-only, needs Google token from vault
  - `calendar_free_slots(days)` — read-only
  - `send_email(to, subject, body)` — **risky**: always goes through ApprovalService first
- **Registry (`registry.py`):**
  - `load_tool(tool_record)` registers a **wrapper function** on the FastMCP instance. The wrapper does **not** import the generated code into the server process; it calls `sandbox.run_tool(name, args)`.
  - `unload_tool(name)`, `list_tools()`.
  - On startup, re-load all `active` tools from DB.
  - Publish `tool_loaded` / `tool_unloaded`.
- (Optional, for the pitch) demonstrate `ctx.elicit()` in one built-in tool to show MCP-native human input. Do **not** use elicitation to collect secrets.

### 6.6 Toolsmith (`toolsmith/`)

**Tool contract (`tool_template.py`) — every generated tool must follow it:**
```python
TOOL_SPEC = {
    "name": "gold_price_pkr",
    "description": "Return the current gold price per tola in PKR.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
    "secrets_required": [],                 # names only, e.g. ["serpapi_key"]
    "allowed_domains": ["example-gold-site.pk"],
    "risk_level": "low",                    # low | medium | high
    "composed_from": []                     # existing tool names it calls
}

def run(args: dict, ctx) -> dict:
    # ctx.http_get(url, params=None) / ctx.http_post(...) -> enforce allowed_domains
    # ctx.secret("name") -> value injected by sandbox, only if allowed
    # ctx.call_tool("other_tool", {...}) -> composition
    ...
    return {"ok": True, "data": ...}
```

**Pipeline (`pipeline.py`):**
1. `toolsmith_stage: builder` → Builder writes code + spec.
2. **Static check** (`static_check.py`):
   - AST checker blocks: `import os/subprocess/socket/shutil/ctypes/requests/urllib`, `eval`, `exec`, `open(..., "w")`, `__import__`, `getattr` tricks, printing/logging anything returned by `ctx.secret`, string literals that look like keys, URLs whose domain is not in `allowed_domains`.
   - Run `bandit` on the file.
   - Max 2 automatic builder retries if the static check fails; feed the errors back.
3. `toolsmith_stage: tester` → Tester writes tests; run with pytest in the sandbox. Max 2 retries.
4. `toolsmith_stage: critic` → Critic gets code + static report + test output → `CriticReport`.
5. `toolsmith_stage: awaiting_review` → `ApprovalService.request(kind="new_tool", risk=spec.risk_level, details={code, spec, tests, test_output, static_report, critic_report})`.
6. If the tool needs secrets not in the vault → publish `secret_requested`; UI shows `SecretForm`; wait for it.
7. Approved → save under `generated_tools/<name>/v<N>/`, insert `ToolRecord(status="active")`, `registry.load_tool`, `toolsmith_stage: loaded`.
   Rejected → `toolsmith_stage: rejected` with the human's note; the Worker is told the capability was denied and must continue without it or escalate.
8. **Self-repair:** if an active tool raises at runtime, the runner may start the pipeline in `repair` mode with the error + old code; the approval card shows a **diff** between versions.

**Sandbox (`sandbox.py`):**
- Run `python -I runner_shim.py <tool_dir>` as a subprocess with timeout `SANDBOX_TIMEOUT_SEC`, a clean temp working dir, minimal env (no API keys except the specific secrets this tool is allowed), args passed as JSON on stdin, result read as JSON on stdout.
- `runner_shim.py` builds the `ctx` object: `http_get/http_post` check the domain against `allowed_domains` before calling httpx; `secret()` reads only the injected allowed secrets; `call_tool()` calls back to the backend via a local endpoint.
- Every secret injection publishes `secret_used {tool, secret_name, domain}` (never the value) and animates the vault edge on the System Map.
- (Stretch) run the subprocess in Docker with `--network` limited.

### 6.7 Vault (`vault/`)
- Fernet-encrypted values in SQLite; master key from `.env`.
- `put(name, value, allowed_tools, allowed_domains, permission, expires_at)`, `get_for_tool(name, tool_name, domain)` (enforces scope), `revoke(name)` (deletes + disables dependent tools), `list()` (masked), `audit_log()`.
- When a tool asks for a secret it is not scoped for → `ApprovalService.request(kind="secret_access")`: *"`gold_emailer` wants your Gmail token. Allow?"*
- **Secrets are entered only via `POST /api/vault/secrets` from `SecretForm`** — never through chat, never through the LLM.
- **Google OAuth** (`google_oauth.py`): `/api/oauth/google/start` → Google consent page → `/callback` stores the token in the vault as `google_token` with scopes. Start with read-only scopes; request `gmail.send` only when a tool needs it (permission escalation = approval).

### 6.8 Voice (`voice/tts.py`, `routes_voice.py`)
- `POST /api/voice/speak {text, role}` → streams MP3 from ElevenLabs (Flash model). Three voices: Orchestrator, Builder, Critic.
- **Phrase cache:** on startup (or via a script) generate fixed lines once and save to `audio_cache/` ("New tool needs your approval", "Critic flagged a risk", "Task complete", "Branch paused", ...). Serve cached audio when text matches.
- Dev mode flag `VOICE_PROVIDER=browser` → frontend uses `speechSynthesis` instead, to save credits.
- The Narrator publishes `speak` events for important moments only (approval needed, critic block, tool loaded, run finished). Rate-limit: max 1 line per 4 seconds.
- **Voice commands** are parsed by an OpenAI call into an intent:
  `{"intent": "new_goal|approve|reject|show_code|pause|resume|prune|status|explain", "target": "...", "text": "..."}`
  `POST /api/voice/command {transcript}` executes it.

### 6.9 API summary
```
POST /api/goals                 {goal} -> {run_id}
GET  /api/runs/{run_id}         snapshot (nodes, approvals)
POST /api/agents/{id}/control   {action: pause|resume|prune|redirect|inject, text?}
GET  /api/approvals?status=pending
POST /api/approvals/{id}/decide {decision, note, confirm, edited_payload?}
GET  /api/tools                 POST /api/tools/{name}/disable
GET  /api/vault/secrets         POST /api/vault/secrets   DELETE /api/vault/secrets/{name}
GET  /api/vault/audit
GET  /api/oauth/google/start    GET /api/oauth/google/callback
POST /api/voice/speak           POST /api/voice/command
WS   /ws/{run_id}
```

---

## 7. Frontend — "Mission Control"

Dark, cinematic, single page. Layout: top bar (goal input, voice orb, run status, cost meter) · center (Agent Tree / System Map toggle) · right (Approval Inbox) · bottom (Swimlanes) · drawers (Tool Library, Vault, Node Details).

- **Zustand store** is built only from WebSocket events (`applyEvent(event)` reducer). This makes replay free: reconnecting replays the same events.
- **AgentTree:** React Flow custom node showing role icon, short goal, status color, confidence bar, token count. Colors: thinking = blue, running_tool = amber, waiting_human = purple **pulsing**, done = green, failed = red, paused = grey, pruned = faded. New nodes animate in (Framer Motion scale/fade); layout recomputed with dagre top-to-bottom. Toolsmith runs appear as a special purple sub-branch (Builder → Tester → Critic → Human). Click a node → `NodeDetails` drawer with goal, tool calls, results, and buttons Pause / Resume / Prune / Redirect / Add note.
- **SystemMap:** fixed nodes — Browser, Orchestrator, Agents, FastMCP, Tool Registry, Sandbox, Vault, OpenAI, SerpAPI, Google, ElevenLabs. On each `system_flow` event animate a glowing particle along the edge (animated SVG edge). Vault → Sandbox edge glows gold on `secret_used`.
- **Swimlanes:** one row per agent, horizontal time axis, bars for active periods, icons for tool calls and human waits. Overlapping bars make parallelism obvious. Filters: agent, type, "human events only".
- **ApprovalInbox / ApprovalCard:** for `new_tool` show tabs: Code (Monaco; diff view for repairs), Spec (domains, secrets, risk), Tests (output), Critic (issues with line highlights in Monaco). Buttons: Approve, Reject (requires note), Edit. High-risk approvals require a click even after voice approval. Badge count in the top bar.
- **ToolLibrary:** cards for every tool: built-in vs grown, approver, date, usage count, `composed_from` lineage graph, disable button. Header counter: "Started with N tools · Humans approved M".
- **VaultPanel:** masked secrets, scopes, expiry, last used, audit log, Revoke. `SecretForm` is a password input posting straight to `/api/vault/secrets`.
- **VoiceOrb:** click to start (also unlocks browser audio autoplay). Mic via Web Speech API → transcript → `/api/voice/command`. On `speak` events fetch `/api/voice/speak`, play, and animate the orb from an `AnalyserNode`. Show live transcript under the orb.
- **Explain mode:** "Why did you do that?" → backend returns an ordered list of node ids + sentences; the frontend highlights each node while the line plays.
- **Replay mode:** load a past `run_id` and play events back with a speed slider. This is also the backup demo if internet fails.

---

## 8. Build phases

### Phase 0 — Skeleton (target: 2 h)
- Repo layout, `.env.example`, backend FastAPI with `/health`, frontend Next.js with Tailwind + shadcn, dark theme.
- EventBus + `/ws/{run_id}` + SQLite events table.
- A `/api/debug/fake_run` endpoint that emits a scripted sequence of fake events.
- Frontend store + AgentTree rendering the fake run live.
**Acceptance:** opening the page and hitting fake_run shows nodes appearing and changing color in real time; refreshing the page replays them.

### Phase 1 — Real recursive, parallel orchestrator (target: 4 h)
- Planner + Worker agents, DAG execution with TaskGroup + Semaphore, recursion with `MAX_DEPTH`, budgets, confidence.
- FastMCP mounted with `web_search` and `fetch_url`; Workers use them via MCP.
- Agent controls: pause, resume, prune, redirect.
**Acceptance:** goal "Compare the price of a MacBook Air at 3 Pakistani stores" spawns ≥3 parallel workers visible at the same time in the tree; pruning a branch cancels only that branch; a low-confidence answer creates an approval.

### Phase 2 — Approvals (target: 2 h)
- ApprovalService, approval routes, ApprovalInbox UI, `send_email` as a risky built-in (can be a mock that logs instead of sending).
**Acceptance:** while one branch waits for approval, the others keep running and finishing.

### Phase 3 — Toolsmith (target: 6 h) ← the core of the demo
- Tool contract, sandbox + shim, static checker + bandit, Builder/Tester/Critic agents, pipeline, registry hot-load, ApprovalCard with Code/Spec/Tests/Critic tabs.
**Acceptance:**
- Goal "What is the gold price per tola in PKR right now?" with no gold tool → pipeline runs → approval card shows code, passing tests, critic report → approve → tool appears in the MCP tool list without restarting → worker uses it → answer appears.
- A deliberately malicious build (see demo script) is **blocked** by the static checker or critic, and the human can reject it.
- Rejecting a tool makes the worker continue gracefully.

### Phase 4 — Vault + Google OAuth (target: 3 h)
- Vault, SecretForm, scoped access approvals, audit log, revoke; Google OAuth flow; `gmail_search`, `calendar_free_slots`.
**Acceptance:** a generated tool that needs a secret pauses, the secret form appears, the value is stored encrypted, the tool runs, the audit log shows the use, the value never appears in any event, log, or prompt (grep the DB to verify).

### Phase 5 — System Map, Swimlanes, Tool Library (target: 4 h)
**Acceptance:** during a run, particles move along the correct edges; swimlanes show overlapping bars for parallel agents; the tool library shows lineage and the approval counter.

### Phase 6 — Voice (target: 3 h)
- Voice orb, Web Speech API commands, intent parser, ElevenLabs TTS with three voices, phrase cache, browser fallback.
**Acceptance:** saying "Banyan, track the gold price every hour" starts a run; the critic's warning is spoken in the critic's voice; saying "approve" works for low-risk but high-risk still needs a click.

### Phase 7 — Polish (remaining time)
- Tool composition ("email the gold chart to my team every Friday" reuses existing tools, builds only glue; schedule via APScheduler).
- Self-repair with diff view.
- Explain mode, replay mode, cost meter, loading states, empty states, error toasts.
- Record a full backup demo video.

**If time runs out, cut from the bottom.** Phases 0–3 are the minimum winning product.

---

## 9. Demo script (≈4 minutes)

1. **Intro (20s):** "Most agents fail when they lack a tool. Banyan builds the tool — and a human decides if it's allowed to exist."
2. **Gold tracker (60s):** voice: "Banyan, what's the gold price in PKR?" → tree grows → Toolsmith branch → approval card → show tests + critic → approve → tool loaded → answer spoken.
3. **Parallelism (40s):** "Compare a MacBook Air across 3 stores" → three parallel branches, one pauses for approval while the others finish.
4. **Safety moment (40s):** a prepared request causes the builder to write a tool that sends data to an unknown domain or logs a secret → static checker / critic flags it red, Critic voice warns → human rejects.
5. **Vault (30s):** secret form, masked vault, audit log, revoke.
6. **Composition (30s):** "Email the gold price to my team every Friday" → only glue code built → approve (high risk: email) → scheduled.
7. **Close (20s):** Tool Library: "Started with 5 tools. Humans approved 9." System Map glowing.

Prepare the malicious example in advance (a seeded prompt or a debug flag that injects a bad tool), so the safety moment is reliable.

---

## 10. Rules for Claude Code while building

- Work phase by phase; finish acceptance checks before moving on. Commit after each phase.
- Keep API keys in `.env` only; never log secret values; never pass secret values into any prompt.
- All UI state comes from events. If the UI needs something, emit an event for it.
- Generated tool code is **never** imported into the main server process — always run through the sandbox.
- Keep prompts in one place (`agents.py`) as constants so we can tune them quickly.
- Use structured outputs (Pydantic) for every agent; handle validation errors with one retry.
- Add `try/except` around every external call (OpenAI, SerpAPI, Google, ElevenLabs) and emit a `log` event with a readable error instead of crashing a branch.
- Use cheap models by default; allow overriding the Builder/Critic model via `OPENAI_MODEL_STRONG`.
- Write a short `README.md` with setup steps: install, `.env`, run backend (`uvicorn app.main:app --reload`), run frontend (`pnpm dev`), Google OAuth console setup.