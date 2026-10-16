"""Phase 3 acceptance (Toolsmith) against a running server in mock mode.
Usage: python tests/e2e_phase3.py [base_url]"""
import sys
import threading
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def start(goal):
    run_id = uuid.uuid4().hex[:10]
    out = {}
    t = threading.Thread(target=lambda: out.update(
        httpx.post(f"{BASE}/api/goals", json={"goal": goal, "run_id": run_id}, timeout=300).json()))
    t.start()
    return run_id, t, out


def pending(run_id, kind=None):
    rows = httpx.get(f"{BASE}/api/approvals?status=pending&run_id={run_id}", timeout=30).json()
    rows = [r for r in rows if kind is None or r["kind"] == kind]
    return rows[0] if rows else None


def wait_for(cond, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(1)
    raise AssertionError("timed out")


def decide(a, decision, **kw):
    return httpx.post(f"{BASE}/api/approvals/{a['id']}/decide", json={"decision": decision, **kw}, timeout=30)


def active_tools():
    return [t["name"] for t in httpx.get(f"{BASE}/api/tools", timeout=30).json()["grown"] if t["status"] == "active"]


httpx.post(f"{BASE}/api/tools/gold_price_pkr/disable", timeout=30)  # start clean (404 is fine)
assert "gold_price_pkr" not in active_tools()

# --- 1. missing tool -> build -> tests -> critic -> human approves -> hot-loaded -> used ---
run_id, t, out = start("What is the gold price per tola in PKR right now?")
a = wait_for(lambda: pending(run_id, "new_tool"))
d = a["details"]
assert not d["blocked"] and d["tests_passed"] == d["tests_total"] == 2, d
assert d["critic_report"]["verdict"] == "pass" and "goldprice.example.pk" in d["spec"]["allowed_domains"]
assert "gold_price_pkr" not in active_tools()  # nothing exists before the human decides
assert decide(a, "approved").status_code == 200
t.join(240)
assert "gold_price_pkr" in active_tools(), "tool was not hot-loaded"
assert "245,000" in (out.get("result") or ""), out
print("PASS toolsmith: built, tested, critic passed, human approved, hot-loaded, used ->", out["result"][:70])

# --- 2. malicious build is blocked and can only be rejected ---
httpx.post(f"{BASE}/api/tools/gold_price_pkr/disable", timeout=30)
run_id, t, out = start("What is the gold price per tola in PKR right now? sneaky")
a = wait_for(lambda: pending(run_id, "new_tool"))
d = a["details"]
assert d["blocked"] and a["risk"] == "high", a
msgs = " ".join(i["message"] for i in d["static_report"])
assert "evil-analytics.net" in msgs, d["static_report"]
assert decide(a, "approved", confirm=True).status_code == 400  # cannot approve a blocked build
assert decide(a, "rejected", note="exfiltrates data").status_code == 200
low = wait_for(lambda: pending(run_id, "low_confidence"))  # worker continues without the tool
decide(low, "approved")
t.join(240)
assert "gold_price_pkr" not in active_tools()
print("PASS safety: malicious tool blocked by static check, approval refused, rejection let the run continue")
