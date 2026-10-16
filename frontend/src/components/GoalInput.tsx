"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { useBanyan } from "@/store/useBanyan";

const newRunId = () => crypto.randomUUID().replace(/-/g, "").slice(0, 10);

export default function GoalInput({ onRun }: { onRun: (runId: string) => void }) {
  const runStatus = useBanyan((s) => s.runStatus);
  const pending = useBanyan((s) => Object.values(s.approvals).filter((a) => a.status === "pending").length);
  const [goal, setGoal] = useState("");

  // The client picks the run id: the backend executes the whole run inside this one request
  // (serverless has no background tasks) while the page polls for events.
  const launch = (url: string, body?: object) => {
    const runId = newRunId();
    onRun(runId);
    fetch(`${API_URL}${url.replace("{id}", runId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify({ ...body, run_id: runId }) : undefined,
    }).catch((err) => console.error("Could not reach backend", err));
  };

  return (
    <header className="flex items-center gap-3 border-b border-slate-800 px-5 py-3">
      <span className="text-lg font-semibold tracking-tight">🌳 Banyan</span>
      <form
        className="flex flex-1 gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (goal.trim()) launch("/api/goals", { goal: goal.trim() });
        }}
      >
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Give Banyan a goal…  e.g. Compare the price of a MacBook Air at 3 Pakistani stores"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm outline-none focus:border-emerald-500"
        />
        <button className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500">
          Run
        </button>
      </form>
      <button
        onClick={() => launch("/api/debug/fake_run/{id}")}
        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
      >
        Fake run
      </button>
      {pending > 0 && (
        <span className="rounded-full bg-purple-600 px-2.5 py-0.5 text-xs font-medium">{pending} need you</span>
      )}
      <span className="text-xs uppercase tracking-wide text-slate-400">{runStatus}</span>
    </header>
  );
}
