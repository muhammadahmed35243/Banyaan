"""Static security checker for generated tools: our own AST rules + bandit.

Returns a report {ok, issues:[{line, severity, message, source}]}. `ok` is False if any
issue has severity "block". The checker is deliberately an allowlist (imports) plus a
denylist (calls / attributes) - it is a first barrier; the sandbox is the second."""
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWED_IMPORTS = {
    "json", "re", "math", "datetime", "decimal", "statistics", "collections", "itertools",
    "functools", "typing", "html", "textwrap", "string",
}
BANNED_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "breakpoint", "input", "print", "memoryview",
}
KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"),
]
URL_RE = re.compile(r"https?://([A-Za-z0-9.\-]+)", re.I)


def _issue(line: int, message: str, severity: str = "block", source: str = "ast") -> dict:
    return {"line": line, "severity": severity, "message": message, "source": source}


def _domain_allowed(host: str, allowed: list[str]) -> bool:
    host = host.lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed)


def extract_spec(tree: ast.Module) -> dict | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "TOOL_SPEC" for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
    return None


def _is_secret_call(n: ast.AST) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "secret")


def ast_check(code: str) -> tuple[list[dict], dict | None]:
    issues: list[dict] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [_issue(e.lineno or 1, f"Syntax error: {e.msg}")], None

    spec = extract_spec(tree)
    if spec is None:
        issues.append(_issue(1, "TOOL_SPEC missing or not a literal dict"))
    else:
        for k in ("name", "description", "input_schema", "secrets_required", "allowed_domains", "risk_level"):
            if k not in spec:
                issues.append(_issue(1, f"TOOL_SPEC missing key '{k}'"))
    runs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run"]
    if not runs or [a.arg for a in runs[0].args.args] != ["args", "ctx"]:
        issues.append(_issue(1, "run(args, ctx) must be defined at module level"))
    allowed = list((spec or {}).get("allowed_domains", []))

    tainted: set[str] = set()  # names holding a secret value
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 1)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    issues.append(_issue(line, f"Import of '{a.name}' is not allowed"))
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                issues.append(_issue(line, f"Import from '{node.module}' is not allowed"))
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in BANNED_CALLS:
                issues.append(_issue(line, f"Call to '{f.id}' is not allowed"))
            if isinstance(f, ast.Attribute) and f.attr in ("system", "popen", "exec_module", "read_text", "write_text"):
                issues.append(_issue(line, f"Call to '.{f.attr}' is not allowed"))
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            issues.append(_issue(line, f"Private or dunder attribute '{node.attr}' is not allowed"))
        elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id != "__name__":
            issues.append(_issue(line, f"Dunder name '{node.id}' is not allowed"))
        elif isinstance(node, ast.Assign) and _is_secret_call(node.value):
            tainted.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.lineno > 0:
            s = node.value
            for pat in KEY_PATTERNS:
                if pat.search(s):
                    issues.append(_issue(line, "String literal looks like a hard-coded key or token"))
                    break
            for host in URL_RE.findall(s):
                if not _domain_allowed(host, allowed):
                    issues.append(_issue(line, f"URL domain '{host}' is not in allowed_domains"))

    # Secrets must never flow into return values (and so never into events/logs/prompts).
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            if names & tainted or any(_is_secret_call(n) for n in ast.walk(node.value)):
                issues.append(_issue(node.lineno, "A secret value is returned from the tool"))
    return issues, spec


def bandit_check(code: str) -> list[dict]:
    """Run bandit on the file; any failure to run it is reported as a warning, not a pass."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "tool.py"
        f.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-m", "bandit", "-q", "-f", "json", str(f)],
                               capture_output=True, text=True, timeout=30)
            data = json.loads(r.stdout or "{}")
        except Exception as e:
            return [_issue(1, f"bandit could not run ({type(e).__name__})", "warn", "bandit")]
    sev = {"HIGH": "block", "MEDIUM": "warn", "LOW": "info"}
    return [_issue(x["line_number"], f"{x['test_id']}: {x['issue_text']}", sev.get(x["issue_severity"], "info"), "bandit")
            for x in data.get("results", [])]


def static_check(code: str, with_bandit: bool = True) -> dict:
    issues, spec = ast_check(code)
    if with_bandit:
        issues += bandit_check(code)
    return {"ok": not any(i["severity"] == "block" for i in issues), "issues": issues, "spec": spec}
