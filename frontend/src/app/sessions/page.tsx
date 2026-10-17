"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import NewSessionButton from "@/components/NewSessionButton";
import { API_URL } from "@/lib/config";

interface SessionSummary {
  id: string;
  goals: number;
  first_goal: string;
  last_goal: string;
  recent_goals: string[];
  agents: number;
  pending: number;
  watching: number;
  started_at: string;
  last_at: string;
}

function ago(iso: string): string {
  // Stored times are UTC; some rows come back without a zone marker.
  const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch(`${API_URL}/api/sessions`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((d: SessionSummary[]) => { if (alive) { setSessions(d); setError(""); } })
        .catch((e: Error) => { if (alive) setError(e.message); });
    load();
    const t = setInterval(load, 10000); // watchers and running goals change the badges
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-4">
          <Link href="/" className="text-lg font-bold tracking-tight hover:text-af-medium">🌳 Banyan</Link>
          <span className="text-sm text-slate-500">/ Sessions</span>
          <div className="flex-1" />
          <NewSessionButton className="rounded-lg bg-af-blue px-4 py-2 text-sm font-medium text-white hover:bg-af-blue-hover">
            + New session
          </NewSessionButton>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        <h1 className="text-3xl font-bold tracking-tight text-af-cream">Sessions</h1>
        <p className="mt-1 text-sm text-slate-400">
          Each session is one workspace: its goals, agents, watchers and approvals. Open one to pick up where it left off.
        </p>

        {error && (
          <div className="mt-8 rounded-xl border border-af-apricot/40 bg-slate-900 p-4 text-sm text-af-apricot">
            Could not load sessions ({error}). Check that the API is reachable, then refresh.
          </div>
        )}

        {!sessions && !error && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => <div key={i} className="h-40 animate-pulse rounded-xl border border-slate-800 bg-slate-900" />)}
          </div>
        )}

        {sessions && sessions.length === 0 && (
          <div className="mt-8 rounded-xl border border-dashed border-slate-700 p-10 text-center">
            <p className="text-slate-300">No sessions yet.</p>
            <NewSessionButton className="mt-4 rounded-lg bg-af-blue px-4 py-2 text-sm font-medium text-white hover:bg-af-blue-hover">
              Start your first session
            </NewSessionButton>
          </div>
        )}

        {sessions && sessions.length > 0 && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions.map((s) => (
              <Link key={s.id} href={`/session?id=${s.id}`}
                className="group flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-5 transition-colors hover:border-af-medium">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="line-clamp-2 font-semibold text-af-cream group-hover:text-af-medium">{s.first_goal || "Untitled session"}</h2>
                  <span className="whitespace-nowrap text-[11px] text-slate-500">{ago(s.last_at)}</span>
                </div>
                {s.goals > 1 && (
                  <ul className="mt-3 space-y-1 text-xs text-slate-400">
                    {s.recent_goals.filter((g) => g !== s.first_goal).slice(-3).map((g, i) => (
                      <li key={i} className="truncate">↳ {g}</li>
                    ))}
                  </ul>
                )}
                <div className="flex-1" />
                <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="text-slate-400">{s.goals} goal{s.goals === 1 ? "" : "s"} · {s.agents} agent{s.agents === 1 ? "" : "s"}</span>
                  {s.watching > 0 && (
                    <span className="rounded-full bg-af-sky/15 px-2 py-0.5 text-af-sky">👁 {s.watching} watching</span>
                  )}
                  {s.pending > 0 && (
                    <span className="rounded-full bg-af-apricot/15 px-2 py-0.5 text-af-apricot">{s.pending} waiting for you</span>
                  )}
                </div>
                <code className="mt-2 text-[10px] text-slate-600">{s.id}</code>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
