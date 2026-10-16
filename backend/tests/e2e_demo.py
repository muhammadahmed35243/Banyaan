"""Stage demo checks: the scripted Toolsmith demo (good + unsafe) works on any server,
including production with a real LLM. Usage: python tests/e2e_demo.py [base_url]"""
import sys
import threading
import time
import uuid

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8002"
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def run(sneaky: bool):
    rid, out = uuid.uuid4().hex[:10], {}
    t = threading.Thread(target=lambda: out.update(httpx.post(
        f"{base}/api/debug/toolsmith_demo", json={"run_id": rid, "sneaky": sneaky}, timeout=None).json()))
    t.start()
    seen = None
    end = time.time() + 120
    while t.is_alive() and time.time() < end:
        for a in httpx.get(f"{base}/api/approvals?status=pending&run_id={rid}").json():
            if a["kind"] == "new_tool":
                seen = a
            if a["details"].get("blocked"):
                r = httpx.post(f"{base}/api/approvals/{a['id']}/decide", json={"decision": "approved", "confirm": True})
                check("blocked build cannot be approved", r.status_code == 400)
                httpx.post(f"{base}/api/approvals/{a['id']}/decide", json={"decision": "rejected", "note": "unsafe"})
            else:
                httpx.post(f"{base}/api/approvals/{a['id']}/decide", json={"decision": "approved", "confirm": True})
        time.sleep(1)
    t.join(10)
    return out, seen


out, card = run(False)
check("toolsmith demo built a tool and asked a human", card and card["kind"] == "new_tool" and not card["details"]["blocked"])
check("approved tool was hot-loaded and used", "245,000" in str(out.get("result")), str(out))
lib = httpx.get(f"{base}/api/tools").json()
g = next((t for t in lib["grown"] if t["name"] == "gold_price_pkr"), None)
check("tool library shows lineage", g and g["approved_by"] == "human" and g["tests_passed"] == g["tests_total"], str(g)[:200])

out, card = run(True)
check("unsafe build was blocked", card and card["details"]["blocked"], str(card)[:200])
check("run continued after rejecting it", out.get("run_id") is not None)

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
