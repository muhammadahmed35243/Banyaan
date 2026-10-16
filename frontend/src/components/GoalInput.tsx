"use client";

import { API_URL } from "@/lib/config";
import { useBanyan } from "@/store/useBanyan";

export default function GoalInput({ onRun }: { onRun: (runId: string) => void }) {
  const runStatus = useBanyan((s) => s.runStatus);

  const start = () => {
    // The client picks the run id: the backend plays the scripted run inside this one
    // request (no background tasks on serverless) while we poll for its events.
    const runId = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    onRun(runId);
    fetch(`${API_URL}/api/debug/fake_run/${runId}`, { method: "POST" }).catch((err) =>
      console.error("Could not reach backend", err),
    );
  };

  return (
    <header className="flex items-center gap-4 border-b border-slate-800 px-5 py-3">
      <span className="text-lg font-semibold tracking-tight">🌳 Banyan</span>
      <button
        onClick={start}
        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
      >
        Run fake run
      </button>
      <span className="text-xs uppercase tracking-wide text-slate-400">{runStatus}</span>
    </header>
  );
}
