"""The contract every generated tool must follow. Kept as text so it can be placed in the
Builder's prompt verbatim."""

TOOL_CONTRACT = '''
A tool is ONE Python file defining TOOL_SPEC (a literal dict) and run(args, ctx).

TOOL_SPEC = {
    "name": "gold_price_pkr",                 # snake_case, unique
    "description": "Return the current gold price per tola in PKR.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
    "secrets_required": [],                   # names only, e.g. ["serpapi_key"]
    "allowed_domains": ["example-gold-site.pk"],   # every URL you touch must be here
    "risk_level": "low",                      # low | medium | high
    "composed_from": []                       # existing tool names it calls
}

def run(args: dict, ctx) -> dict:
    # ctx.http_get(url, params=None, headers=None) -> {"status": int, "text": str}
    # ctx.http_post(url, json=None, headers=None)  -> {"status": int, "text": str}
    # ctx.secret("name") -> str, only if listed in secrets_required and approved
    # ctx.call_tool("other_tool", {...}) -> dict
    return {"ok": True, "data": ...}

RULES: only import json, re, math, datetime, decimal, statistics, collections, itertools,
functools, typing, html, textwrap, string. No file access, no eval/exec/getattr, no dunder
attributes, no print. Never return, log or embed a secret in output. Hard-coded keys are
forbidden. Network ONLY through ctx.http_get / ctx.http_post to allowed_domains.
'''
