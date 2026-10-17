"use client";

import { useState } from "react";
import Link from "next/link";
import { launchDemo, launchFakeRun, launchGoal } from "@/lib/actions";
import { useBanyan } from "@/store/useBanyan";
import DemoGuide from "./DemoGuide";
import SimulateEmail from "./SimulateEmail";
import ToolLibrary from "./ToolLibrary";
import VoiceOrb from "./VoiceOrb";

export default function GoalInput({ sessionId, onNewSession }: { sessionId: string; onNewSession: () => void }) {
  const pending = useBanyan((s) => Object.values(s.approvals).filter((a) => a.status === "pending").length);
  const running = useBanyan((s) => Object.values(s.runs).filter((r) => r.status === "running").length);
  const watching = useBanyan((s) => Object.values(s.nodes)
    .filter((n) => n.role === "watcher" && n.status === "watching").length);
  const [goal, setGoal] = useState("");
  const [guide, setGuide] = useState(false);

  // The input stays free after submitting, so more goals can run in parallel.
  return (
    <header className="relative z-10 flex items-center gap-2 border-b bg-slate-900 shadow-[0_1px_8px_rgba(16,24,40,0.05)] [&_button]:whitespace-nowrap border-slate-800 px-5 py-3">
      <Link href="/" className="whitespace-nowrap text-lg font-bold tracking-tight hover:text-af-medium">🌳 Banyan</Link>
      <Link href="/sessions" className="whitespace-nowrap text-xs text-slate-400 hover:text-af-medium">← Sessions</Link>
      <VoiceOrb sessionId={sessionId} />
      <form
        className="flex min-w-[10rem] flex-1 gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!goal.trim()) return;
          launchGoal(sessionId, goal.trim());
          setGoal("");
        }}
      >
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Give Banyan a goal… goals run side by side. e.g. Any time I get an email about a payment, tell me"
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm outline-none focus:border-af-medium"
        />
        <button className="rounded-lg bg-af-blue px-3 py-1.5 text-sm font-medium text-white hover:bg-af-blue-hover">
          Run
        </button>
      </form>
      <button onClick={() => launchDemo(sessionId)} title="Start a watcher and a parallel price comparison"
        className="rounded-lg bg-af-dark px-3 py-1.5 text-xs font-medium text-white hover:bg-af-blue">▶ Demo</button>
      <button onClick={() => setGuide((g) => !g)} title="Presentation script"
        className="rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-800">📋 Script</button>
      <button onClick={() => launchFakeRun(sessionId)} title="Scripted run, no AI calls"
        className="hidden rounded-lg 2xl:block border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
        Fake run
      </button>
      {watching > 0 && <SimulateEmail />}
      <ToolLibrary />
      {pending > 0 && (
        <span className="whitespace-nowrap rounded-full bg-purple-600 px-2.5 py-0.5 text-xs font-medium">{pending} need you</span>
      )}
      <span className="whitespace-nowrap text-xs text-slate-400">
        {running} running{watching > 0 && <span className="text-af-sky"> · {watching} watching</span>}
      </span>
      <button onClick={onNewSession} title="Start a clean session"
        className="whitespace-nowrap rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800">
        New session
      </button>
      {guide && <DemoGuide sessionId={sessionId} onClose={() => setGuide(false)} />}
    </header>
  );
}
