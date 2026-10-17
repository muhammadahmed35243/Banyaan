"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/config";
import { decide } from "@/lib/actions";
import type { Approval } from "@/store/useBanyan";

interface D {
  service: string; label: string; why: string; auth: string; known: boolean;
  base_url?: string | null; google_enabled: boolean; demo: boolean; access: string;
  needs_base_url?: boolean; base_hint?: string | null; token_hint?: string | null;
}

/** A goal needs the user's own account somewhere (Classroom, GitHub, any API). Google services
 * reuse "Sign in with Google" (adding only that service's read access); anything else takes a
 * token. The credential goes straight to the vault; agents only ever see the data. */
export default function ConnectServiceCard({ a }: { a: Approval }) {
  const d = a.details as unknown as D;
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState(d.base_url ?? "");
  const [auth, setAuth] = useState("bearer");
  const [header, setHeader] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const input = "w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs outline-none focus:border-af-medium";

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.banyan === "google") {
        setBusy(false);
        if (!e.data.ok) setErr("Sign-in did not grant access. Try again and allow every permission; if Google says "
          + "'access blocked', add your account as a test user and enable the API in Google Cloud.");
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const send = async (body: object) => {
    setErr("");
    setBusy(true);
    const r = await fetch(`${API_URL}/api/approvals/${a.id}/service_credential`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    setBusy(false);
    if (!r.ok) setErr((await r.json().catch(() => ({}))).detail ?? "Failed");
  };

  return (
    <div className="rounded-lg border-l-4 border-af-sky bg-slate-900 p-3 text-sm">
      <div className="text-[10px] uppercase tracking-wide text-af-sky">🔌 connect a service · {a.risk} risk</div>
      <div className="mt-1 font-medium">{a.title}</div>
      <p className="mt-1 text-xs text-slate-300">Banyan wants to {d.why.charAt(0).toLowerCase() + d.why.slice(1).replace(/\.+$/, "")}.</p>
      <p className="mt-1 text-xs text-slate-400">{d.access}</p>

      {d.auth === "google" ? (
        <button disabled={busy || !d.google_enabled}
          onClick={() => {
            setBusy(true); setErr("");
            window.open(`${API_URL}/api/auth/google/start?approval_id=${a.id}&service=${d.service}`, "banyan-google",
              "width=520,height=680");
          }}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded bg-white px-2 py-1.5 text-xs font-medium text-slate-900 hover:bg-slate-200 disabled:opacity-50">
          <span className="font-bold text-blue-600">G</span>
          {busy ? "Waiting for Google…" : `Sign in with Google (read ${d.label})`}
        </button>
      ) : (
        <form className="mt-2 space-y-1.5" autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            send({ token, base_url: d.known && !d.needs_base_url ? undefined : baseUrl,
              auth: d.known ? undefined : auth, header: d.known ? undefined : header || undefined });
          }}>
          {d.needs_base_url && (
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={d.base_hint ?? "https://…"} className={input} />
          )}
          {!d.known && (
            <>
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="API base URL (https://…)" className={input} />
              <div className="flex gap-1.5">
                <select value={auth} onChange={(e) => setAuth(e.target.value)} className={input}>
                  <option value="bearer">Authorization: Bearer</option>
                  <option value="header">Custom header</option>
                  <option value="query">Query parameter</option>
                </select>
                {auth !== "bearer" && (
                  <input value={header} onChange={(e) => setHeader(e.target.value)}
                    placeholder={auth === "header" ? "Header name (X-API-Key)" : "Param name (api_key)"} className={input} />
                )}
              </div>
            </>
          )}
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="new-password"
            name={`svc-token-${a.id}`} placeholder={d.token_hint ?? `${d.label} API token`} className={input} />
          <button disabled={busy || !token || ((!d.known || d.needs_base_url) && !baseUrl)}
            className="w-full rounded bg-af-blue px-2 py-1.5 text-xs font-medium text-white hover:bg-af-blue-hover disabled:opacity-40">
            Connect {d.label}
          </button>
        </form>
      )}

      {d.demo && (
        <button disabled={busy} onClick={() => send({ use_demo: true })}
          className="mt-2 w-full rounded bg-cyan-800 px-2 py-1.5 text-xs text-white hover:bg-cyan-700 disabled:opacity-40">
          Use demo Classroom (for presentations)
        </button>
      )}

      <div className="mt-2 flex gap-2">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (to deny)" className={input} />
        <button disabled={!note} onClick={async () => { const r = await decide(a.id, "rejected", { note }); if (!r.ok) setErr(r.detail); }}
          className="rounded bg-red-700 px-2 py-1 text-xs hover:bg-red-600 disabled:opacity-40">Deny</button>
      </div>
      {err && <div className="mt-1 text-xs text-red-600">{err}</div>}
    </div>
  );
}
