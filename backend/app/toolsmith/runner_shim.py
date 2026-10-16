"""Runs INSIDE the sandbox subprocess (python -I runner_shim.py <tool.py>).

Reads {"args", "secrets", "allowed_domains"} as JSON on stdin, loads the tool file, runs
run(args, ctx) and prints one JSON line after RESULT_MARKER. The ctx object is the tool's
only door to the outside world: domain-checked HTTP, scoped secrets, tool composition."""
import importlib.util
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

RESULT_MARKER = "@@BANYAN_RESULT@@"


def _domain_ok(host: str, allowed: list[str]) -> bool:
    host = (host or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed)


_json = json  # tool-facing parameters named `json` shadow the module below


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # a redirect could leave the allowed domain
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _http(method: str, url: str, params=None, headers=None, body=None) -> dict:
    # Standard library only: the sandbox runs in isolated mode (-I), which on serverless hosts
    # cannot see the server's site-packages (no httpx here).
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        r = _opener.open(req, timeout=15)
        return {"status": r.status, "text": r.read(200_000).decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "text": e.read(200_000).decode("utf-8", "replace")}


def make_ctx(secrets: dict, allowed: list[str], used: list[str], mock_http: dict | None = None):
    def check(url: str) -> None:
        host = urlparse(url).hostname or ""
        if not _domain_ok(host, allowed):
            raise PermissionError(f"domain '{host}' is not in allowed_domains")

    def mocked(url):
        # Test mode: canned responses by URL substring, no network at all.
        for needle, resp in (mock_http or {}).items():
            if needle in url:
                return resp
        raise PermissionError(f"no mock response for {url}")

    def http_get(url, params=None, headers=None):
        check(url)
        if mock_http is not None:
            return mocked(url)
        return _http("GET", url, params, headers)

    def http_post(url, json=None, headers=None):  # noqa: A002 - mirrors the common kwarg
        check(url)
        if mock_http is not None:
            return mocked(url)
        h = {"Content-Type": "application/json", **(headers or {})}
        return _http("POST", url, None, h, _json.dumps(json).encode() if json is not None else None)

    def secret(name):
        if name not in secrets:
            raise PermissionError(f"secret '{name}' is not available to this tool")
        used.append(name)
        return secrets[name]

    def call_tool(name, args=None):
        raise NotImplementedError("tool composition is not enabled yet")

    class Ctx:  # secrets live in the closure, not on the object
        pass

    ctx = Ctx()
    ctx.http_get, ctx.http_post, ctx.secret, ctx.call_tool = http_get, http_post, secret, call_tool
    return ctx


def main() -> None:
    payload = json.loads(sys.stdin.read())
    used: list[str] = []
    try:
        spec = importlib.util.spec_from_file_location("banyan_tool", sys.argv[1])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ctx = make_ctx(payload.get("secrets", {}), payload.get("allowed_domains", []), used,
                       payload.get("mock_http"))
        data = mod.run(payload.get("args", {}), ctx)
        out = {"ok": True, "data": data, "secrets_used": used}
    except Exception as e:  # report, never crash silently
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500], "secrets_used": used}
    sys.stdout.write("\n" + RESULT_MARKER + json.dumps(out, default=str) + "\n")


main()
