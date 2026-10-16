"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import type { Approval } from "@/store/useBanyan";

/**
 * A watcher asks for mailbox access. What the human types goes straight to the encrypted
 * vault (POST .../credential); no agent and no LLM ever sees it.
 */
export default function WatchSetupCard({ a }: { a: Approval }) {
  const d = a.details as {
    service: string; condition: string; access: string; interval_sec: number;
    has_credential: boolean; credential_label: string | null;
  };
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const post = async (url: string, body: object) => {
    setErr("");
    setBusy(true);
    const r = await fetch(`${API_URL}${url}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!r || !r.ok) setErr((await r?.json().catch(() => ({})))?.detail ?? "Failed");
  };
  const [topic, setTopic] = useState("");
  const credential = (body: object) =>
    post(`/api/approvals/${a.id}/credential`, { ...body, ntfy_topic: topic || undefined });

  const input = "mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs";
  return (
    <div className="rounded-lg border-l-4 border-cyan-400 bg-slate-900 p-3 text-sm">
      <div className="text-[10px] uppercase tracking-wide text-cyan-300">🔐 credential request · {a.risk} risk</div>
      <div className="mt-1 font-medium">{a.title}</div>
      <p className="mt-1 text-xs text-slate-300">
        Alert you about emails <b>{d.condition}</b>. Checks every ~{d.interval_sec}s.
      </p>
      <p className="mt-1 text-xs text-slate-400">{d.access} The password goes into the encrypted vault; agents never see it.</p>

      {d.has_credential ? (
        <div className="mt-2 rounded bg-slate-950 p-2 text-xs text-slate-300">
          Vault already holds <b>{d.credential_label}</b>.
          <button disabled={busy} onClick={() => post(`/api/approvals/${a.id}/decide`, { decision: "approved", confirm: true })}
            className="ml-2 rounded bg-emerald-600 px-2 py-0.5 hover:bg-emerald-500 disabled:opacity-50">Use it</button>
        </div>
      ) : null}

      <form className="mt-2" autoComplete="off" onSubmit={(e) => { e.preventDefault(); credential({ mode: "imap", email, app_password: pw }); }}>
        {/* No autofill: a browser must not silently drop some other saved login in here. */}
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" className={input}
          name={`watch-email-${a.id}`} autoComplete="off" />
        <input value={pw} onChange={(e) => setPw(e.target.value)} type="password" autoComplete="new-password"
          name={`watch-app-pw-${a.id}`}
          placeholder="Gmail app password (16 letters)" className={input} />
        <div className="mt-1 text-[10px] text-slate-500">
          Google Account → Security → 2-Step Verification → App passwords.
        </div>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} autoComplete="off"
          name={`watch-ntfy-${a.id}`} placeholder="Optional: ntfy topic for phone alerts (tab closed)" className={input} />
        <div className="mt-1 text-[10px] text-slate-500">
          Install the ntfy app, subscribe to a long random topic name, paste it here. Alert text is sent via ntfy.sh.
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <button disabled={busy || !email || !pw} className="rounded bg-emerald-600 px-2 py-1 text-xs hover:bg-emerald-500 disabled:opacity-40">
            Connect Gmail
          </button>
          <button type="button" disabled={busy} onClick={() => credential({ mode: "demo" })}
            className="rounded bg-cyan-700 px-2 py-1 text-xs hover:bg-cyan-600 disabled:opacity-40">Use demo inbox</button>
        </div>
      </form>
      <div className="mt-2 flex gap-2">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (to deny)" className={input} />
        <button disabled={busy || !note} onClick={() => post(`/api/approvals/${a.id}/decide`, { decision: "rejected", note })}
          className="mt-1 rounded bg-red-700 px-2 py-1 text-xs hover:bg-red-600 disabled:opacity-40">Deny</button>
      </div>
      {busy && <div className="mt-1 text-xs text-slate-400">Connecting…</div>}
      {err && <div className="mt-1 text-xs text-red-400">{err}</div>}
    </div>
  );
}
