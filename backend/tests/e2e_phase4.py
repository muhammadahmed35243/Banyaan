"""Phase 4 e2e: a session with parallel goals + a standing watcher agent.
Needs a server with MOCK_LLM=1 (WATCH_INTERVAL_SEC=3 makes it quick).
Usage: python tests/e2e_phase4.py [base_url]"""
import sys
import threading
import time
import uuid

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
c = httpx.Client(base_url=base, timeout=120)
sid = uuid.uuid4().hex[:10]
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def events():
    return c.get(f"/api/sessions/{sid}/events?after=0").json()["events"]


def start(goal):
    rid = uuid.uuid4().hex[:10]
    out = {}
    t = threading.Thread(target=lambda: out.update(httpx.post(
        f"{base}/api/goals", json={"goal": goal, "run_id": rid, "session_id": sid}, timeout=None).json()))
    t.start()
    return rid, t, out


def wait(pred, secs=60):
    end = time.time() + secs
    while time.time() < end:
        r = pred()
        if r:
            return r
        time.sleep(1)
    return None


# 1. Two goals in one session, running at the same time.
w_rid, w_thread, w_out = start("Any time I get an email related to payment, tell me")
time.sleep(1)
c_rid, c_thread, c_out = start("Compare the price of a MacBook Air at 3 Pakistani stores")

# 2. The watcher asks for inbox access; the compare run keeps going meanwhile.
card = wait(lambda: next((a for a in c.get(f"/api/approvals?status=pending&run_id={w_rid}").json()
                          if a["kind"] == "watch_setup"), None))
check("watcher asks for a credential", card is not None)
check("approval card holds no secret", card and "app_password" not in str(card["details"]))
if not card["details"]["has_credential"]:  # first time: plain approve must be refused
    r = c.post(f"/api/approvals/{card['id']}/decide", json={"decision": "approved", "confirm": True})
    check("approve without a credential is refused", r.status_code == 400 and "credential" in r.json()["detail"])
r = c.post(f"/api/approvals/{card['id']}/credential", json={"mode": "demo"})
check("credential stored in vault", r.status_code == 200, r.text)
w_thread.join(60)
check("watch goal returns while the watcher keeps running", "watcher" in str(w_out.get("result", "")).lower(), str(w_out))

ev = events()
watcher = next((e["agent_id"] for e in ev if e["type"] == "agent_spawned" and e["payload"].get("role") == "watcher"), None)
check("watcher node in the tree", watcher is not None)
check("watcher status is watching", any(e["type"] == "agent_status" and e["agent_id"] == watcher
                                         and e["payload"]["status"] == "watching" for e in ev))
check("both runs share one session stream", {w_rid, c_rid} <= {e["run_id"] for e in ev})
check("vault list shows label only", all("ciphertext" not in v for v in c.get("/api/vault").json()))

# 3. Mail arrives: a payment and a newsletter. Only the payment should alert.
c.post("/api/demo/emails", json={"preset": "newsletter"})
c.post("/api/demo/emails", json={"preset": "payment"})


def alerts():
    c.post(f"/api/sessions/{sid}/tick")
    return [e for e in events() if e["type"] == "alert"] or None


got = wait(alerts, 40)
check("payment email raises an alert", bool(got))
check("newsletter does not alert", got and all("newsletter" not in a["payload"]["subject"].lower() and
                                               "AI" not in a["payload"]["subject"] for a in got))
check("alert has the amount", got and "14,250" in str(got[0]["payload"].get("amount")))

# 3b. The watcher proposes a follow-up; nothing happens until a human approves it.
prop = wait(lambda: next((a for a in c.get(f"/api/approvals?status=pending&run_id={w_rid}").json()
                          if a["kind"] == "watch_action"), None), 20)
check("watcher proposes an action", prop is not None and prop["details"]["action"] == "track_bill", str(prop)[:200])
check("no bill before approval", c.get(f"/api/sessions/{sid}/bills").json() == [])
if prop:
    c.post(f"/api/approvals/{prop['id']}/decide", json={"decision": "approved", "confirm": True})
bills = c.get(f"/api/sessions/{sid}/bills").json()
check("approved action adds the bill", len(bills) == 1 and bills[0]["status"] == "due", str(bills))
check("bill_tracked event emitted", any(e["type"] == "bill_tracked" for e in events()))
check("cron endpoint refuses without the secret", c.post("/api/watches/tick_all").status_code == 401)

# 4. The watcher is controllable like any agent.
c.post(f"/api/agents/{watcher}/control", json={"action": "pause"})
c.post("/api/demo/emails", json={"preset": "receipt"})
time.sleep(4)
c.post(f"/api/sessions/{sid}/tick")
time.sleep(2)
check("paused watcher does not check", len([e for e in events() if e["type"] == "alert"]) == len(got or []))
c.post(f"/api/agents/{watcher}/control", json={"action": "resume"})
more = wait(lambda: (lambda a: a if len(a) > len(got or []) else None)(alerts() or []), 40)
check("resumed watcher catches mail that arrived while paused", bool(more))
c.post(f"/api/agents/{watcher}/control", json={"action": "prune"})
w = c.get(f"/api/sessions/{sid}/watches").json()
check("prune stops the watcher", w and w[0]["status"] == "stopped", str(w))

# 5. The other goal finished on its own, in parallel.
end = time.time() + 120
while c_thread.is_alive() and time.time() < end:
    for a in c.get(f"/api/approvals?status=pending&run_id={c_rid}").json():  # its low-confidence card
        c.post(f"/api/approvals/{a['id']}/decide", json={"decision": "approved", "confirm": True})
    time.sleep(1)
check("parallel compare goal finished", c_out.get("result") is not None, str(c_out)[:200])

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
