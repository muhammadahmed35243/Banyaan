"""Phase 1 acceptance check against a running server (MOCK_LLM=1 uvicorn app.main:app).
Usage: python tests/e2e_phase1.py [base_url]"""
import sys
import threading
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
GOAL = "Compare the price of a MacBook Air at 3 Pakistani stores"


def start(goal):
    run_id = uuid.uuid4().hex[:10]
    out = {}
    t = threading.Thread(target=lambda: out.update(
        httpx.post(f"{BASE}/api/goals", json={"goal": goal, "run_id": run_id}, timeout=180).json()))
    t.start()
    return run_id, t, out


def events(run_id):
    return httpx.get(f"{BASE}/api/runs/{run_id}/events?after=0", timeout=30).json()["events"]


def statuses(evs):
    st = {}
    for e in evs:
        if e["type"] == "agent_spawned":
            st[e["agent_id"]] = "queued"
        elif e["type"] == "agent_status" and "status" in e["payload"]:
            st[e["agent_id"]] = e["payload"]["status"]
        elif e["type"] == "agent_finished":
            st[e["agent_id"]] = "done"
        elif e["type"] == "agent_failed":
            st[e["agent_id"]] = "failed"
    return st


def wait_for(cond, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(0.7)
    raise AssertionError("timed out")


# --- 1. parallelism + low-confidence approval while other branches finish ---
run_id, t, out = start(GOAL)
st = wait_for(lambda: (s := statuses(events(run_id))) and
              sum(v in ("thinking", "running_tool") for k, v in s.items() if ".t" in k) >= 3 and s)
print("PASS parallel: 3 workers active at once")

appr = wait_for(lambda: httpx.get(f"{BASE}/api/approvals?status=pending&run_id={run_id}").json())
assert appr[0]["kind"] == "low_confidence", appr
s = statuses(events(run_id))
done = [k for k, v in s.items() if ".t" in k and v == "done"]
assert len(done) == 2, s
print("PASS approval: one branch waits for a human while 2 others finished")

r = httpx.post(f"{BASE}/api/approvals/{appr[0]['id']}/decide", json={"decision": "approved"})
assert r.status_code == 200, r.text
t.join(60)
assert out.get("result"), out
assert events(run_id)[-1]["type"] == "run_finished"
print("PASS run finished after approval:", out["result"][:60])

# --- 2. prune cancels only that branch ---
run_id, t, out = start(GOAL)
wait_for(lambda: sum(v in ("thinking", "running_tool") for k, v in statuses(events(run_id)).items() if ".t" in k) >= 3)
target = f"{run_id}-root.t1"
assert httpx.post(f"{BASE}/api/agents/{target}/control", json={"action": "prune"}).status_code == 200
wait_for(lambda: statuses(events(run_id)).get(target) == "pruned", 20)
appr = wait_for(lambda: httpx.get(f"{BASE}/api/approvals?status=pending&run_id={run_id}").json())
httpx.post(f"{BASE}/api/approvals/{appr[0]['id']}/decide", json={"decision": "approved"})
t.join(60)
s = statuses(events(run_id))
assert s[target] == "pruned" and s[f"{run_id}-root.t2"] == "done" and s[f"{run_id}-root.t3"] == "done", s
print("PASS prune: only the pruned branch was cancelled; run still finished")
