"""Runs generated tools in a separate Python process: isolated mode (-I), clean temp cwd,
minimal environment (no API keys - only the secrets this tool is allowed), hard timeout.
Generated code is NEVER imported into the server process.

Limits (documented honestly): this is process isolation + static checking, not a
kernel-level jail; a stretch goal is Docker / Vercel Sandbox for network egress control."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..config import settings


RESULT_MARKER = "@@BANYAN_RESULT@@"  # must match runner_shim.py
SHIM = Path(__file__).with_name("runner_shim.py")
MAX_OUTPUT = 1_000_000


def _run_sync(tool_file: Path, args: dict, secrets: dict, allowed_domains: list[str], timeout: float,
              mock_http: dict | None = None) -> dict:
    env = {"PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":  # python on Windows will not start without these
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    payload = json.dumps({"args": args, "secrets": secrets, "allowed_domains": allowed_domains,
                          "mock_http": mock_http})
    with tempfile.TemporaryDirectory() as cwd:
        try:
            p = subprocess.run([sys.executable, "-I", str(SHIM), str(tool_file)], input=payload,
                               capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timeout after {timeout}s", "secrets_used": []}
    out = p.stdout[-MAX_OUTPUT:]
    if RESULT_MARKER not in out:
        return {"ok": False, "error": f"tool crashed: {p.stderr.strip()[-300:] or 'no output'}", "secrets_used": []}
    return json.loads(out.rsplit(RESULT_MARKER, 1)[1].strip())


async def run_tool(tool_file: Path, args: dict, secrets: dict | None = None,
                   allowed_domains: list[str] | None = None, timeout: float | None = None,
                   mock_http: dict | None = None) -> dict:
    return await asyncio.to_thread(_run_sync, Path(tool_file), args, secrets or {},
                                   allowed_domains or [], timeout or settings.sandbox_timeout_sec, mock_http)
