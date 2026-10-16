"""Toolsmith: Builder -> static check -> Tester -> Critic -> human approval -> hot-load.

Each stage is a visible child node under the worker that asked for the tool, plus
`toolsmith_stage` events. Nothing is loaded without a human decision, and builds that the
static checker or Critic block can only be rejected (enforced in routes_approvals)."""
import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .. import approvals, store
from ..events import bus
from ..models import Event, ToolRow
from ..orchestrator.agents import CURRENT, LLM, MissingTool
from .sandbox import run_tool
from .static_check import static_check

MAX_BUILD_ATTEMPTS = 3  # first try + 2 automatic retries
# A generated tool must never shadow a built-in (it would silently replace e.g. send_email).
RESERVED_NAMES = {"web_search", "fetch_url", "calculate", "current_time", "send_email"}


async def _ev(run_id: str, type_: str, agent_id: str | None, parent_id: str | None = None, **payload) -> None:
    await bus.publish(Event(run_id=run_id, type=type_, agent_id=agent_id, parent_id=parent_id, payload=payload))


def _subset(expect, actual) -> bool:
    if isinstance(expect, dict):
        return isinstance(actual, dict) and all(k in actual and _subset(v, actual[k]) for k, v in expect.items())
    return expect == actual


async def run_cases(code: str, spec: dict, cases) -> dict:
    """Run Tester cases in the sandbox with NO network (HTTP is mocked per case).
    (PLAN.md suggests pytest; JSON cases avoid executing LLM-written test code at all.)"""
    results = []
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "tool.py"
        f.write_text(code, encoding="utf-8")
        for c in cases:
            try:
                args, mock, expect = json.loads(c.args_json), json.loads(c.mock_http_json), json.loads(c.expect_json)
            except json.JSONDecodeError as e:
                results.append({"name": c.name, "passed": False, "detail": f"bad test JSON: {e}"})
                continue
            r = await run_tool(f, args, allowed_domains=spec.get("allowed_domains", []), mock_http=mock)
            ok = r["ok"] and _subset(expect, r["data"])
            results.append({"name": c.name, "passed": ok,
                            "detail": "ok" if ok else (r.get("error") or f"got {json.dumps(r['data'])[:200]}")})
    passed = sum(x["passed"] for x in results)
    text = "\n".join(f"{'PASS' if x['passed'] else 'FAIL'}  {x['name']}  {'' if x['passed'] else x['detail']}" for x in results)
    return {"passed": passed, "total": len(results), "results": results, "text": text}


async def build_tool(run_id: str, parent_id: str, hint: MissingTool, llm: LLM) -> ToolRow | None:
    """Returns the newly active ToolRow, or None if it was blocked / rejected."""
    kids = {r: f"{parent_id}.ts-{r}" for r in ("builder", "tester", "critic")}

    async def spawn(role: str, goal: str):
        await _ev(run_id, "agent_spawned", kids[role], parent_id, role=role, goal=goal, depth=99, status="queued")

    async def status(role: str, st: str, **extra):
        await _ev(run_id, "agent_status", kids[role], status=st, **extra)

    await _ev(run_id, "toolsmith_stage", parent_id, stage="builder", tool=hint.name_hint)
    await spawn("builder", f"Write tool '{hint.name_hint}'")
    await spawn("tester", "Write and run tests")
    await spawn("critic", "Security review")

    CURRENT.set((run_id, kids["builder"]))
    request = f"{hint.description}\nSuggested name: {hint.name_hint}\nExample input: {hint.example_input}"
    feedback, code, report, tests = None, "", {"ok": False, "issues": [], "spec": None}, {"passed": 0, "total": 0, "text": "not run", "results": []}

    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        await status("builder", "thinking", attempt=attempt)
        built, _ = await llm.build_tool(request, feedback)
        code = built.code
        report = static_check(code)
        if not report["ok"]:
            feedback = "Static check failed:\n" + "\n".join(f"line {i['line']}: {i['message']}" for i in report["issues"] if i["severity"] == "block")
            await _ev(run_id, "log", kids["builder"], message=f"Static check blocked attempt {attempt}")
            continue
        await status("builder", "done")
        await _ev(run_id, "toolsmith_stage", parent_id, stage="tester")
        await status("tester", "thinking")
        cases, _ = await llm.write_tests(code)
        tests = await run_cases(code, report["spec"], cases.cases)
        if tests["passed"] == tests["total"] and tests["total"] > 0:
            await status("tester", "done")
            break
        feedback = "Tests failed:\n" + tests["text"]
        await _ev(run_id, "log", kids["tester"], message=f"Tests failed on attempt {attempt}")
    else:
        pass  # exhausted attempts: whatever we have goes to the Critic/human flagged accordingly

    blocked = not report["ok"]
    built_name = (report["spec"] or {}).get("name") or hint.name_hint
    if built_name in RESERVED_NAMES:
        blocked = True
        report["issues"].append({"line": 1, "severity": "block", "source": "policy",
                                 "message": f"Tool name '{built_name}' collides with a built-in tool"})
    if blocked:
        await status("builder", "failed")
        await status("tester", "pruned")
    elif tests["passed"] != tests["total"]:
        await status("tester", "failed")

    await _ev(run_id, "toolsmith_stage", parent_id, stage="critic")
    await status("critic", "thinking")
    critic, _ = await llm.critique(code, json.dumps(report["issues"]), tests["text"])
    if critic.verdict == "block":
        blocked = True
        await status("critic", "failed")
        await _ev(run_id, "speak", parent_id, role="critic",
                  text="Critic flagged a risk. This tool was blocked.")
    else:
        await status("critic", "done")
    if tests["passed"] != tests["total"]:
        blocked = True  # never offer a tool that fails its own tests

    spec = report["spec"] or {}
    name = spec.get("name") or hint.name_hint
    risk = "high" if blocked else spec.get("risk_level", "low")
    details = {
        "name": name, "code": code, "spec": spec, "test_output": tests["text"],
        "tests_passed": tests["passed"], "tests_total": tests["total"],
        "static_report": report["issues"],
        "critic_report": {"verdict": critic.verdict, "issues": [i.model_dump() for i in critic.issues]},
        "blocked": blocked,
    }
    await _ev(run_id, "toolsmith_stage", parent_id, stage="awaiting_review", tool=name, blocked=blocked)
    title = f"{'BLOCKED build of' if blocked else 'New tool'}: {name}"
    row = await approvals.request(run_id, parent_id, "new_tool", title, details, risk)

    if row.status == "rejected" or blocked:
        await _ev(run_id, "toolsmith_stage", parent_id, stage="rejected", tool=name, note=row.note)
        await store.save_tool(ToolRow(name=name, status="rejected", code=code, description=spec.get("description", "")))
        return None

    tool = ToolRow(
        name=name, description=spec.get("description", ""), input_schema=spec.get("input_schema", {}),
        secrets_required=spec.get("secrets_required", []), allowed_domains=spec.get("allowed_domains", []),
        risk_level=spec.get("risk_level", "low"), status="active", approved_by="human",
        approved_at=datetime.now(timezone.utc), composed_from=spec.get("composed_from", []),
        code=code, tests={"output": tests["text"], "passed": tests["passed"], "total": tests["total"]})
    await store.save_tool(tool)
    await _ev(run_id, "tool_loaded", parent_id, tool=name, risk=risk)
    await _ev(run_id, "toolsmith_stage", parent_id, stage="loaded", tool=name)
    await _ev(run_id, "speak", parent_id, role="orchestrator",
              text=f"New tool {name} is live. It passed {tests['passed']} tests.")
    await asyncio.sleep(0)
    return tool
