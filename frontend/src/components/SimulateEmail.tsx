"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { simulateEmail } from "@/lib/actions";

const PRESETS = [
  { key: "payment", label: "💳 Bill due (payment)" },
  { key: "receipt", label: "🧾 Payment receipt" },
  { key: "newsletter", label: "📰 Newsletter (should be ignored)" },
  { key: "personal", label: "💬 Personal note (should be ignored)" },
];

const CLASS_PRESETS = [
  { key: "assignment", label: "📚 New assignment" },
  { key: "quiz", label: "📝 New quiz" },
  { key: "announcement", label: "📣 Class announcement" },
];

const simulateClass = (preset: string) =>
  fetch(`${API_URL}/api/demo/classroom/simulate`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preset }),
  });

/** Drops an email into the demo inbox (or posts to the demo Classroom) so a watcher can be shown live in a presentation. */
export default function SimulateEmail() {
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState("");

  const send = async (preset: string, label: string, classroom = false) => {
    setOpen(false);
    await (classroom ? simulateClass(preset) : simulateEmail(preset)).catch(() => {});
    setSent(label);
    setTimeout(() => setSent(""), 4000);
  };

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className="whitespace-nowrap rounded-lg border border-cyan-300 px-3 py-1.5 text-xs text-cyan-800 hover:bg-cyan-50">
        📨 {sent ? `Sent: ${sent}` : "Simulate"}
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-30 w-64 rounded-lg border border-slate-700 bg-slate-950 p-1 shadow-xl">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-slate-500">Send to the demo inbox</div>
          {PRESETS.map((p) => (
            <button key={p.key} onClick={() => send(p.key, p.label)}
              className="block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-slate-800">{p.label}</button>
          ))}
          <div className="mt-1 border-t border-slate-800 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-500">Post to the demo Classroom</div>
          {CLASS_PRESETS.map((p) => (
            <button key={p.key} onClick={() => send(p.key, p.label, true)}
              className="block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-slate-800">{p.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
