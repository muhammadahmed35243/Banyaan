"use client";

import { useState } from "react";
import { simulateEmail } from "@/lib/actions";

const PRESETS = [
  { key: "payment", label: "💳 Bill due (payment)" },
  { key: "receipt", label: "🧾 Payment receipt" },
  { key: "newsletter", label: "📰 Newsletter (should be ignored)" },
  { key: "personal", label: "💬 Personal note (should be ignored)" },
];

/** Drops an email into the demo inbox so a watcher can be shown live in a presentation. */
export default function SimulateEmail() {
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState("");

  const send = async (preset: string, label: string) => {
    setOpen(false);
    await simulateEmail(preset).catch(() => {});
    setSent(label);
    setTimeout(() => setSent(""), 4000);
  };

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className="rounded-lg border border-cyan-800 px-3 py-1.5 text-xs text-cyan-200 hover:bg-cyan-950">
        📨 {sent ? `Sent: ${sent}` : "Simulate email"}
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-30 w-64 rounded-lg border border-slate-700 bg-slate-950 p-1 shadow-xl">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-slate-500">Send to the demo inbox</div>
          {PRESETS.map((p) => (
            <button key={p.key} onClick={() => send(p.key, p.label)}
              className="block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-slate-800">{p.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
