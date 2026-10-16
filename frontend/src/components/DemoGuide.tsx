"use client";

import { useState } from "react";
import { launchDemo, launchToolsmithDemo } from "@/lib/actions";

/** The presentation script as a checklist the presenter can glance at. */
const STEPS: [string, string][] = [
  ["Open", "\"Banyan is a team of AI agents where humans stay in charge. Agents grow their own tools, and a person approves every new capability.\""],
  ["▶ Demo", "Click ▶ Demo. Two goals start side by side: a payment watcher and a 3-store price comparison."],
  ["Parallel agents", "Point at the comparison tree: three researchers search at the same time, an analyst waits for all three, then compares with `calculate`."],
  ["Credential", "The watcher asks for inbox access. Say: \"the password goes into an encrypted vault; the AI never sees it.\" Click Use demo inbox."],
  ["System map", "Switch to 🛰️ System map: particles show agents talking to the LLM, SerpAPI, the inbox. Gold = a secret used by a connector."],
  ["Live email", "📨 Simulate email → Newsletter: nothing happens. Then → Bill due: within ~20 s an alert appears and is spoken."],
  ["Human approves", "The watcher proposes \"Add bill to tracker\". Approve it → the 📒 Bills tracker updates. Nothing happens without a human."],
  ["Voice", "Click 🎙 and say \"status\", then \"show the timeline\". Saying \"approve\" works for low risk; high risk still needs a click."],
  ["Timeline", "📊 Timeline: overlapping bars prove the agents worked in parallel; the watcher's lane keeps running."],
  ["Toolsmith", "Click 🔧 Toolsmith demo below: a worker lacks a gold-price tool → Builder → Tester → Critic → you approve (look at Code / Tests / Critic tabs) → hot-loaded and used."],
  ["Safety", "Click ☠️ Unsafe build: the Builder writes a tool that sends data to an unknown site. Static check + Critic block it; the card can only be rejected."],
  ["Close", "🧰 Tool Library: \"Started with 5 tools · Humans approved N\". Every capability passed a human."],
];

export default function DemoGuide({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [done, setDone] = useState<Set<number>>(new Set());
  const btn = "rounded-lg px-2 py-1.5 text-xs font-medium";
  return (
    <div className="absolute right-4 top-14 z-40 max-h-[75vh] w-[26rem] overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/95 p-4 text-xs shadow-2xl backdrop-blur">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">📋 Demo script (~4 min)</h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200">✕</button>
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        <button onClick={() => launchDemo(sessionId)} className={`${btn} bg-indigo-600 hover:bg-indigo-500`}>▶ Watcher + compare</button>
        <button onClick={() => launchToolsmithDemo(sessionId)} className={`${btn} bg-purple-700 hover:bg-purple-600`}>🔧 Toolsmith demo</button>
        <button onClick={() => launchToolsmithDemo(sessionId, true)} className={`${btn} bg-red-800 hover:bg-red-700`}>☠️ Unsafe build</button>
      </div>
      <p className="mb-2 text-[10px] text-slate-500">
        The Toolsmith buttons use a scripted model so the tool-building loop runs the same way every time on stage.
      </p>
      <ol className="space-y-2">
        {STEPS.map(([title, text], i) => (
          <li key={i} onClick={() => setDone((d) => { const n = new Set(d); if (n.has(i)) n.delete(i); else n.add(i); return n; })}
            className={`cursor-pointer rounded-lg border p-2 ${done.has(i) ? "border-emerald-900 opacity-50" : "border-slate-800 hover:border-slate-600"}`}>
            <div className="font-medium text-slate-200">{done.has(i) ? "✓" : i + 1}. {title}</div>
            <div className="mt-0.5 text-slate-400">{text}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
