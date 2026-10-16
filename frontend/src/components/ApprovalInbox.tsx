"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { useBanyan, type Approval } from "@/store/useBanyan";

function Card({ a }: { a: Approval }) {
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(String(a.details.result ?? ""));
  const [err, setErr] = useState("");

  const decide = async (decision: string, extra: object = {}) => {
    setErr("");
    const r = await fetch(`${API_URL}/api/approvals/${a.id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // confirm:true comes from a real click here; the API requires it for high-risk items.
      body: JSON.stringify({ decision, note: note || undefined, confirm: true, ...extra }),
    });
    if (!r.ok) setErr((await r.json().catch(() => ({}))).detail ?? "Failed");
  };

  const color = a.risk === "high" ? "border-red-500" : a.risk === "medium" ? "border-amber-500" : "border-slate-600";
  return (
    <div className={`rounded-lg border-l-4 ${color} bg-slate-900 p-3 text-sm`}>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">
        {a.kind.replace("_", " ")} · {a.risk} risk
      </div>
      <div className="mt-1 font-medium">{a.title}</div>
      {a.details.result !== undefined && !editing && (
        <p className="mt-2 rounded bg-slate-950 p-2 text-xs text-slate-300">{String(a.details.result)}</p>
      )}
      {editing && (
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          className="mt-2 w-full rounded border border-slate-700 bg-slate-950 p-2 text-xs" />
      )}
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required to reject)"
        className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs" />
      <div className="mt-2 flex gap-2">
        <button onClick={() => decide("approved")} className="rounded bg-emerald-600 px-2 py-1 text-xs hover:bg-emerald-500">Approve</button>
        {a.kind === "low_confidence" && (
          editing ? (
            <button onClick={() => decide("edited", { edited_payload: { result: text } })}
              className="rounded bg-blue-600 px-2 py-1 text-xs hover:bg-blue-500">Save edit</button>
          ) : (
            <button onClick={() => setEditing(true)} className="rounded bg-slate-700 px-2 py-1 text-xs hover:bg-slate-600">Edit</button>
          )
        )}
        <button onClick={() => decide("rejected")} className="rounded bg-red-700 px-2 py-1 text-xs hover:bg-red-600">Reject</button>
      </div>
      {err && <div className="mt-1 text-xs text-red-400">{err}</div>}
    </div>
  );
}

export default function ApprovalInbox() {
  const approvals = useBanyan((s) => s.approvals);
  const pending = Object.values(approvals).filter((a) => a.status === "pending");
  return (
    <aside className="w-80 shrink-0 overflow-y-auto border-l border-slate-800 p-3">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Approval inbox ({pending.length})
      </h2>
      {pending.length === 0 && <p className="text-xs text-slate-500">Nothing needs you right now.</p>}
      <div className="space-y-3">{pending.map((a) => <Card key={a.id} a={a} />)}</div>
    </aside>
  );
}
