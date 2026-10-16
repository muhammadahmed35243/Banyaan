"""Run one real goal against a server and stream its events; auto-approves low-risk approvals.
Usage: python tests/live_goal.py "<goal>" [base_url] [--approve-tools]"""
import sys
import threading
import time
import uuid

import httpx

goal = sys.argv[1]
base = next((a for a in sys.argv[2:] if a.startswith("http")), "http://localhost:8000")
approve_tools = "--approve-tools" in sys.argv
rid = uuid.uuid4().hex[:10]
out = {}
t = threading.Thread(target=lambda: out.update(
    httpx.post(f"{base}/api/goals", json={"goal": goal, "run_id": rid}, timeout=600).json()))
t.start()
seen = 0
t0 = time.time()
while t.is_alive():
    ev = httpx.get(f"{base}/api/runs/{rid}/events?after={seen}", timeout=60).json()
    for e in ev["events"]:
        who = (e["agent_id"] or "").split("-")[-1]
        print(f"[{time.time() - t0:5.0f}s] {e['type']:<16} {who:<22} {str(e['payload'])[:150]}")
    seen = ev["cursor"]
    time.sleep(2)
    for a in httpx.get(f"{base}/api/approvals?status=pending&run_id={rid}", timeout=60).json():
        if a["kind"] == "new_tool" and not approve_tools:
            print(">>> new_tool approval waiting (blocked=%s); pass --approve-tools to auto-approve" % a["details"].get("blocked"))
            continue
        if a["details"].get("blocked"):
            print(">>> rejecting blocked build"); httpx.post(f"{base}/api/approvals/{a['id']}/decide", json={"decision": "rejected", "note": "blocked"}); continue
        print(">>> approving", a["kind"], a["title"])
        httpx.post(f"{base}/api/approvals/{a['id']}/decide", json={"decision": "approved", "confirm": True})
print("RESULT:", out)
