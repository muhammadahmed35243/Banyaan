"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { newId } from "@/lib/ids";
import { useBanyan } from "@/store/useBanyan";
import ToolLibrary from "./ToolLibrary";
import SimulateEmail from "./SimulateEmail";

export default function GoalInput({ sessionId, onNewSession }: { sessionId: string; onNewSession: () => void }) {
  const pending = useBanyan((s) => Object.values(s.approvals).filter((a) => a.status === "pending").length);
  const running = useBanyan((s) => Object.values(s.runs).filter((r) => r.status === "running").length);
  const watching = useBanyan((s) => Object.values(s.nodes)
    .filter((n) => n.role === "watcher" && !["done", "failed", "pruned"].includes(n.status)).length);
  const [goal, setGoal] = useState("");

  // Each goal is a new run in this session. The backend executes the whole run inside this
  // one request (serverless has no background tasks) while the page polls the session.
  // The input stays free, so more goals can run in parallel.
  const launch = (url: string, body?: object) => {
    const runId = newId();
    fetch(`${API_URL}${url.replace("{id}", runId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify({ ...body, run_id: runId, session_id: sessionId }) : undefined,
    }).catch((err) => console.error("Could not reach backend", err));
  };

  return (
    <header className="relative flex items-center gap-3 border-b border-slate-800 px-5 py-3">
      <span className="text-lg font-semibold tracking-tight">🌳 Banyan</span>
      <form
        className="flex flex-1 gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!goal.trim()) return;
          launch("/api/goals", { goal: goal.trim() });
          setGoal("");
        }}
      >
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Give Banyan a goal… goals run side by side. e.g. Any time I get an email about a payment, tell me"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm outline-none focus:border-emerald-500"
        />
        <button className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500">
          Run
        </button>
      </form>
      <button
        onClick={() => launch(`/api/debug/fake_run/{id}?session_id=${sessionId}`)}
        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
      >
        Fake run
      </button>
      {watching > 0 && <SimulateEmail />}
      <ToolLibrary />
      {pending > 0 && (
        <span className="rounded-full bg-purple-600 px-2.5 py-0.5 text-xs font-medium">{pending} need you</span>
      )}
      <span className="text-xs text-slate-400">
        {running} running{watching > 0 && <span className="text-cyan-300"> · {watching} watching</span>}
      </span>
      <button onClick={onNewSession} title="Start a clean session"
        className="rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800">
        New session
      </button>
    </header>
  );
}
