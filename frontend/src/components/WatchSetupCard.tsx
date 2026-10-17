"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/config";
import type { Approval } from "@/store/useBanyan";

/**
 * A watcher asks for mailbox access. Whatever the human provides (a Google sign-in, an app
 * password) goes straight to the encrypted vault; no agent and no LLM ever sees it.
 */
export default function WatchSetupCard({ a }: { a: Approval }) {
  const d = a.details as {
    service: string; condition: string; access: string; interval_sec: number;
    has_credential: boolean; credential_label: string | null;
  };
  const [google, setGoogle] = useState<{ enabled: boolean; connected: string | null }>({ enabled: false, connected: null });
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [topic, setTopic] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [other, setOther] = useState(false);

  const loadGoogle = () =>
    fetch(`${API_URL}/api/auth/google/config`).then((r) => r.json()).then(setGoogle).catch(() => {});
  useEffect(() => {
    loadGoogle();
    // The sign-in popup reports back when it's done.
    const onMsg = (e: MessageEvent) => { if (e.data?.banyan === "google") { setBusy(false); loadGoogle(); } };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const post = async (url: string, body: object) => {
    setErr("");
    setBusy(true);
    const r = await fetch(`${API_URL}${url}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!r || !r.ok) setErr((await r?.json().catch(() => ({})))?.detail ?? "Failed");
  };
  const credential = (body: object) =>
    post(`/api/approvals/${a.id}/credential`, { ...body, ntfy_topic: topic || undefined });

  // A popup, not a redirect: leaving this page would cut the running goal's request.
  const signIn = () => {
    setBusy(true);
    window.open(`${API_URL}/api/auth/google/start?approval_id=${a.id}`, "banyan-google", "width=520,height=680");
  };

  const input = "mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs";
  const btn = "rounded px-2 py-1 text-xs disabled:opacity-40";
  return (
    <div className="rounded-lg border-l-4 border-cyan-400 bg-slate-900 p-3 text-sm">
      <div className="text-[10px] uppercase tracking-wide text-cyan-300">🔐 credential request · {a.risk} risk</div>
      <div className="mt-1 font-medium">{a.title}</div>
      <p className="mt-1 text-xs text-slate-300">
        Alert you about emails <b>{d.condition}</b>. Checks every ~{d.interval_sec}s.
      </p>
      <p className="mt-1 text-xs text-slate-400">{d.access} Credentials go into the encrypted vault; agents never see them.</p>

      <div className="mt-3 flex flex-col gap-2">
        {google.enabled && (
          google.connected ? (
            <button disabled={busy} onClick={() => credential({ mode: "google" })}
              className={`${btn} bg-emerald-600 hover:bg-emerald-500`}>Use Gmail ({google.connected})</button>
          ) : (
            <button disabled={busy} onClick={signIn}
              className={`${btn} flex items-center justify-center gap-2 bg-white font-medium text-slate-900 hover:bg-slate-200`}>
              <span className="font-bold text-blue-600">G</span> Sign in with Google
            </button>
          )
        )}
        {google.enabled && google.connected && (
          <button disabled={busy} onClick={signIn} className="text-[10px] text-slate-500 hover:text-slate-300">
            Use a different Google account
          </button>
        )}
        <button disabled={busy} onClick={() => credential({ mode: "demo" })}
          className={`${btn} bg-cyan-700 hover:bg-cyan-600`}>Use demo inbox (for presentations)</button>
      </div>

      <input value={topic} onChange={(e) => setTopic(e.target.value)} autoComplete="off"
        name={`watch-ntfy-${a.id}`} placeholder="Optional: ntfy topic for phone alerts (tab closed)" className={`${input} mt-3`} />

      <button onClick={() => setOther((o) => !o)} className="mt-2 text-[10px] text-slate-500 hover:text-slate-300">
        {other ? "▾" : "▸"} Other mailbox (IMAP app password)
      </button>
      {other && (
        <form className="mt-1" autoComplete="off" onSubmit={(e) => { e.preventDefault(); credential({ mode: "imap", email, app_password: pw }); }}>
          {/* No autofill: a browser must not silently drop some other saved login in here. */}
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" className={input}
            name={`watch-email-${a.id}`} autoComplete="off" />
          <input value={pw} onChange={(e) => setPw(e.target.value)} type="password" autoComplete="new-password"
            name={`watch-app-pw-${a.id}`} placeholder="App password (16 letters)" className={input} />
          <button disabled={busy || !email || !pw} className={`${btn} mt-2 bg-slate-700 hover:bg-slate-600`}>Connect</button>
        </form>
      )}

      <div className="mt-2 flex gap-2">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (to deny)" className={input} />
        <button disabled={busy || !note} onClick={() => post(`/api/approvals/${a.id}/decide`, { decision: "rejected", note })}
          className={`${btn} mt-1 bg-red-700 hover:bg-red-600`}>Deny</button>
      </div>
      {busy && <div className="mt-1 text-xs text-slate-400">Waiting for sign-in…</div>}
      {err && <div className="mt-1 text-xs text-red-400">{err}</div>}
    </div>
  );
}
