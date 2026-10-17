"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/config";
import { decide } from "@/lib/actions";
import type { Approval } from "@/store/useBanyan";

/** An agent needs Gmail (e.g. to send an email) and nobody signed in yet. The Google token goes
 * straight to the vault; the send itself still waits for its own approval click. */
export default function ConnectGoogleCard({ a }: { a: Approval }) {
  const d = a.details as { purpose: string; subject?: string; access: string };
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.banyan === "google") {
        setBusy(false);
        if (!e.data.ok) setErr("Sign-in did not complete. If Google said 'access blocked', add your account as a test user.");
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  return (
    <div className="rounded-lg border-l-4 border-amber-400 bg-slate-900 p-3 text-sm">
      <div className="text-[10px] uppercase tracking-wide text-amber-300">🔐 sign-in needed · {a.risk} risk</div>
      <div className="mt-1 font-medium">{a.title}</div>
      <p className="mt-1 text-xs text-slate-300">{d.purpose}{d.subject ? ` · “${d.subject}”` : ""}</p>
      <p className="mt-1 text-xs text-slate-400">{d.access} The token goes into the encrypted vault; agents never see it.</p>
      <button disabled={busy}
        onClick={() => { setBusy(true); setErr(""); window.open(`${API_URL}/api/auth/google/start?approval_id=${a.id}`, "banyan-google", "width=520,height=680"); }}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded bg-white px-2 py-1.5 text-xs font-medium text-slate-900 hover:bg-slate-200 disabled:opacity-50">
        <span className="font-bold text-blue-600">G</span> {busy ? "Waiting for Google…" : "Sign in with Google"}
      </button>
      <div className="mt-2 flex gap-2">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (to skip sending)"
          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs" />
        <button disabled={!note} onClick={async () => { const r = await decide(a.id, "rejected", { note }); if (!r.ok) setErr(r.detail); }}
          className="rounded bg-red-700 px-2 py-1 text-xs hover:bg-red-600 disabled:opacity-40">Skip</button>
      </div>
      {err && <div className="mt-1 text-xs text-red-400">{err}</div>}
    </div>
  );
}
