"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { useBanyan, type Approval } from "@/store/useBanyan";
import NewToolCard from "./NewToolCard";
import WatchSetupCard from "./WatchSetupCard";
import ConnectGoogleCard from "./ConnectGoogleCard";
import ConnectServiceCard from "./ConnectServiceCard";
import Markdown from "./Markdown";

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
      {a.details.to !== undefined && (
        <div className="mt-2 space-y-1 rounded bg-slate-950 p-2 text-xs text-slate-300">
          <div><span className="text-slate-500">To:</span> {String(a.details.to)}</div>
          <div><span className="text-slate-500">Subject:</span> {String(a.details.subject)}</div>
          <p className="whitespace-pre-wrap">{String(a.details.body)}</p>
          {a.details.via !== undefined && (
            <div className={String(a.details.via).startsWith("Gmail") ? "text-amber-700" : "text-slate-500"}>
              Sends via {String(a.details.via)}
            </div>
          )}
        </div>
      )}
      {a.details.result !== undefined && !editing && (
        <div className="mt-2 max-h-56 overflow-y-auto rounded bg-slate-950 p-2"><Markdown text={String(a.details.result)} /></div>
      )}
      {editing && (
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          className="mt-2 w-full rounded border border-slate-700 bg-slate-950 p-2 text-xs" />
      )}
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required to reject)"
        className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs" />
      <div className="mt-2 flex gap-2">
        <button onClick={() => decide("approved")} className="rounded bg-af-blue px-2 py-1 text-xs font-medium text-white hover:bg-af-blue-hover">Approve</button>
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
      {err && <div className="mt-1 text-xs text-red-600">{err}</div>}
    </div>
  );
}

function Bills() {
  const bills = useBanyan((s) => s.bills);
  if (bills.length === 0) return null;
  const num = (a: string) => Number(a.replace(/[^\d.]/g, "")) || 0;
  const due = bills.filter((b) => b.status === "due");
  const currency = (bills[0].amount.match(/^[^\d\s]+/) ?? ["PKR"])[0];
  return (
    <div className="mb-4">
      <h2 className="mb-2 flex justify-between text-xs font-semibold uppercase tracking-wide text-emerald-700">
        <span>📒 Bills tracker</span>
        <span>{due.length} due · {currency} {due.reduce((s, b) => s + num(b.amount), 0).toLocaleString()}</span>
      </h2>
      <div className="space-y-1">
        {bills.map((b) => (
          <div key={b.id} className="flex justify-between rounded bg-slate-900 px-2 py-1.5 text-xs">
            <span className="truncate">{b.payee}{b.dueDate && <span className="text-slate-500"> · due {b.dueDate}</span>}</span>
            <span className={b.status === "paid" ? "text-emerald-600" : "text-amber-700"}>
              {b.amount} {b.status === "paid" ? "✓ paid" : "due"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function NotifyToggle() {
  const watching = useBanyan((s) => Object.values(s.nodes).some((n) => n.role === "watcher" && n.status === "watching"));
  const [perm, setPerm] = useState(() => (typeof Notification === "undefined" ? "denied" : Notification.permission));
  if (!watching || perm !== "default") return null;
  return (
    <button onClick={() => Notification.requestPermission().then(setPerm)}
      className="mb-3 w-full rounded border border-cyan-200 px-2 py-1.5 text-xs text-cyan-800 hover:bg-cyan-50">
      🔔 Show desktop notifications for alerts
    </button>
  );
}

function Alerts() {
  const alerts = useBanyan((s) => s.alerts);
  const dismissed = useBanyan((s) => s.dismissed);
  const { dismiss, select } = useBanyan.getState();
  const live = alerts.filter((a) => !dismissed.has(a.id));
  if (live.length === 0) return null;
  return (
    <div className="mb-4">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-cyan-700">🔔 Alerts ({live.length})</h2>
      <div className="space-y-2">
        {live.map((a) => (
          <div key={a.id} onClick={() => select(a.id)}
            className="cursor-pointer rounded-lg border-l-4 border-cyan-400 bg-cyan-50 p-3 text-xs">
            <div className="flex justify-between gap-2">
              <span className="font-medium text-slate-100">{a.subject}</span>
              {a.amount && <span className="shrink-0 rounded bg-cyan-800 px-1.5 text-cyan-800">{a.amount}</span>}
            </div>
            <div className="mt-0.5 text-slate-400">{a.sender} · {new Date(a.ts).toLocaleTimeString()}</div>
            <p className="mt-1 text-slate-300">{a.summary}</p>
            <button onClick={(e) => { e.stopPropagation(); dismiss(a.id); }}
              className="mt-1 text-[10px] text-slate-500 hover:text-slate-300">Dismiss</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ApprovalInbox() {
  const approvals = useBanyan((s) => s.approvals);
  const pending = Object.values(approvals).filter((a) => a.status === "pending");
  return (
    <aside className={`${pending.length ? "w-96" : "w-64"} shrink-0 overflow-y-auto border-l border-slate-800 bg-slate-900 p-3 transition-all`}>
      <NotifyToggle />
      <Alerts />
      <Bills />
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Approval inbox ({pending.length})
      </h2>
      {pending.length === 0 && <p className="text-xs text-slate-500">Nothing needs you right now.</p>}
      <div className="space-y-3">
        {pending.map((a) =>
          a.kind === "new_tool" ? <NewToolCard key={a.id} a={a} />
            : a.kind === "watch_setup" ? <WatchSetupCard key={a.id} a={a} />
              : a.kind === "connect_google" ? <ConnectGoogleCard key={a.id} a={a} />
              : a.kind === "connect_service" ? <ConnectServiceCard key={a.id} a={a} />
              : <Card key={a.id} a={a} />)}
      </div>
    </aside>
  );
}
