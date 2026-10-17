"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import type { Approval } from "@/store/useBanyan";

interface Issue { line: number; severity: string; message: string; source?: string }
interface ToolDetails {
  name: string;
  code: string;
  spec: Record<string, unknown>;
  test_output: string;
  tests_passed: number;
  tests_total: number;
  static_report: Issue[];
  critic_report: { verdict: string; issues: Issue[] };
  blocked: boolean;
}

const TABS = ["Code", "Spec", "Tests", "Critic"] as const;
const sevColor = (s: string) =>
  s === "block" ? "text-red-400" : s === "warn" ? "text-amber-400" : "text-slate-400";

export default function NewToolCard({ a }: { a: Approval }) {
  const d = a.details as unknown as ToolDetails;
  const [tab, setTab] = useState<(typeof TABS)[number]>("Code");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const issues = [...(d.static_report ?? []).filter((i) => i.severity !== "info"), ...(d.critic_report?.issues ?? [])];
  const flagged = new Set(issues.filter((i) => i.severity !== "info").map((i) => i.line));

  const decide = async (decision: "approved" | "rejected") => {
    setErr("");
    const r = await fetch(`${API_URL}/api/approvals/${a.id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note: note || undefined, confirm: true }),
    });
    if (!r.ok) setErr((await r.json().catch(() => ({}))).detail ?? "Failed");
  };

  const spec = d.spec ?? {};
  return (
    <div className={`rounded-lg border-l-4 bg-slate-900 p-3 text-sm ${d.blocked ? "border-red-500" : "border-purple-500"}`}>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">
        new tool · {a.risk} risk · tests {d.tests_passed}/{d.tests_total} · critic {d.critic_report?.verdict}
      </div>
      <div className="mt-1 font-medium">{a.title}</div>
      {d.blocked && (
        <div className="mt-2 rounded bg-red-950 p-2 text-xs text-red-300">
          Blocked by the security checks. It cannot be approved, only rejected.
        </div>
      )}
      <div className="mt-2 flex gap-1 border-b border-slate-800">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-2 py-1 text-xs ${tab === t ? "border-b-2 border-purple-400 text-white" : "text-slate-400"}`}>
            {t}
          </button>
        ))}
      </div>
      <div className="mt-2 max-h-64 overflow-auto rounded bg-slate-950 p-2 font-mono text-[11px] leading-5">
        {tab === "Code" &&
          d.code.split("\n").map((l, i) => (
            <div key={i} className={flagged.has(i + 1) ? "bg-red-950/70" : ""}>
              <span className="mr-2 select-none text-slate-600">{i + 1}</span>{l}
            </div>
          ))}
        {tab === "Spec" && (
          <dl className="space-y-1 font-sans text-xs">
            <div><dt className="inline text-slate-400">Name: </dt><dd className="inline">{String(spec.name)}</dd></div>
            <div><dt className="inline text-slate-400">Will contact: </dt>
              <dd className="inline">{((spec.allowed_domains as string[]) ?? []).join(", ") || "nothing"}</dd></div>
            <div><dt className="inline text-slate-400">Secrets needed: </dt>
              <dd className="inline">{((spec.secrets_required as string[]) ?? []).join(", ") || "none"}</dd></div>
            <div><dt className="inline text-slate-400">Risk: </dt><dd className="inline">{String(spec.risk_level)}</dd></div>
            <div><dt className="inline text-slate-400">Description: </dt><dd className="inline">{String(spec.description)}</dd></div>
          </dl>
        )}
        {tab === "Tests" && <pre className="whitespace-pre-wrap">{d.test_output}</pre>}
        {tab === "Critic" && (
          <ul className="space-y-1 font-sans text-xs">
            {issues.length === 0 && <li className="text-slate-400">No issues reported.</li>}
            {issues.map((i, k) => (
              <li key={k} className={sevColor(i.severity)}>
                line {i.line} · {i.severity}{i.source ? ` · ${i.source}` : ""}: {i.message}
              </li>
            ))}
            {d.critic_report?.issues.filter((i) => i.severity === "info").map((i, k) => (
              <li key={`i${k}`} className="text-slate-400">note: {i.message}</li>
            ))}
          </ul>
        )}
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required to reject)"
        className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs" />
      <div className="mt-2 flex gap-2">
        {!d.blocked && (
          <button onClick={() => decide("approved")} className="rounded bg-af-blue px-2 py-1 text-xs font-medium text-white hover:bg-af-blue-hover">
            Approve tool
          </button>
        )}
        <button onClick={() => decide("rejected")} className="rounded bg-red-700 px-2 py-1 text-xs hover:bg-red-600">Reject</button>
      </div>
      {err && <div className="mt-1 text-xs text-red-400">{err}</div>}
    </div>
  );
}
