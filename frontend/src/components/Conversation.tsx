"use client";

import { useEffect, useRef, useState } from "react";
import { launchGoal } from "@/lib/actions";
import { API_URL } from "@/lib/config";
import { useBanyan } from "@/store/useBanyan";
import Markdown from "./Markdown";

const ACTIVE = ["queued", "thinking", "running_tool", "waiting_human", "paused"];

/** Save an answer (e.g. a solved assignment) as a .md file the user can edit and submit. */
function download(goal: string, text: string) {
  const name = goal.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "banyan-answer";
  const url = URL.createObjectURL(new Blob([`# ${goal}\n\n${text}\n`], { type: "text/markdown" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}.md`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** What Banyan remembers in this session ("Budget: under 15k PKR"). Every later goal sees these;
 * the human can delete any of them. */
function MemoryStrip({ sessionId }: { sessionId: string }) {
  const memory = useBanyan((s) => s.memory);
  const [open, setOpen] = useState(false);
  if (memory.length === 0) return null;
  const forget = async (i: number) => {
    const r = await fetch(`${API_URL}/api/sessions/${sessionId}/memory/${i}`, { method: "DELETE" });
    if (r.ok) useBanyan.getState().setMemory((await r.json()).facts ?? []);
  };
  return (
    <div className="border-b border-slate-800 px-4 py-2 text-xs">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 text-left text-slate-400 hover:text-slate-200">
        <span className="whitespace-nowrap">🧠 Remembers {memory.length} thing{memory.length === 1 ? "" : "s"}</span>
        {!open && <span className="truncate text-slate-500">· {memory.join(" · ")}</span>}
        <span className="ml-auto">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {memory.map((f, i) => (
            <li key={`${i}-${f}`} className="flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900 py-0.5 pl-2.5 pr-1 text-slate-200">
              {f}
              <button onClick={() => forget(i)} title="Forget this" className="rounded-full px-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200">×</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The session as a conversation: each goal, live progress of its agents, then the answer.
 * Follow-ups use the session's memory, so "and under 15 lac?" works. */
export default function Conversation({ sessionId }: { sessionId: string }) {
  const runs = useBanyan((s) => s.runs);
  const nodes = useBanyan((s) => s.nodes);
  const { select, setView } = useBanyan.getState();
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const list = Object.values(runs).sort((a, b) => a.startedAt - b.startedAt);
  const lastResult = list[list.length - 1]?.result;

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [list.length, lastResult]);
  // A ticking clock while something runs, so "still working" is visibly alive.
  const anyRunning = list.some((r) => r.status === "running");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [anyRunning]);

  return (
    <aside className="flex w-[34%] min-w-[22rem] max-w-[36rem] shrink-0 flex-col border-r border-slate-800 bg-slate-900">
      <h2 className="border-b border-slate-800 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        💬 Conversation
      </h2>
      <MemoryStrip sessionId={sessionId} />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {list.length === 0 && (
          <p className="text-xs text-slate-500">Ask anything. Several goals can run at once; follow-ups remember this session.</p>
        )}
        {list.map((r) => {
          const mine = Object.values(nodes).filter((n) => n.id.startsWith(r.id));
          const working = mine.filter((n) => ACTIVE.includes(n.status));
          const waiting = mine.filter((n) => n.status === "waiting_human").length;
          const watcher = mine.find((n) => n.role === "watcher" && n.status === "watching");
          const secs = Math.max(0, Math.round((now - r.startedAt) / 1000));
          // The server stops a goal at ~270s; past 6 minutes with no answer, its request was lost.
          const lost = r.status === "running" && secs > 360 && waiting === 0;
          return (
            <div key={r.id} className="space-y-2">
              <div className="ml-10 rounded-2xl rounded-tr-sm bg-af-blue px-3 py-2 text-sm text-white">{r.goal}</div>
              <div className="mr-4 rounded-2xl rounded-tl-sm border border-slate-800 bg-slate-900 px-3 py-2">
                {r.result ? (
                  <Markdown text={r.result} />
                ) : lost ? (
                  <p className="text-sm text-amber-700">This goal stopped without an answer (the server request was cut off). Ask again.</p>
                ) : r.status === "finished" ? (
                  <p className="text-sm text-red-700">This goal did not finish (a branch failed or was rejected). Click a red node for details.</p>
                ) : (
                  <div className="text-xs text-slate-400">
                    <span className="animate-pulse">●</span> {working.length} agent{working.length === 1 ? "" : "s"} working · {secs}s
                    {waiting > 0 && <span className="text-purple-700"> · {waiting} waiting for you →</span>}
                    <ul className="mt-1 space-y-0.5">
                      {working.slice(0, 6).map((n) => (
                        <li key={n.id} className="truncate"><span className="text-slate-500">{n.role}</span> · {n.goal}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {watcher && <p className="mt-1 text-xs text-cyan-700">👁 Watcher is still running for this goal.</p>}
                <div className="mt-1 flex items-center gap-3 text-[10px] text-slate-500">
                  <button onClick={() => { setView("tree"); select(`${r.id}-root`); }} className="hover:text-slate-300">
                    {mine.length} agents · show tree
                  </button>
                  {r.result && (
                    <button onClick={() => download(r.goal, r.result!)} title="Save this answer as a Markdown file"
                      className="hover:text-af-medium">⬇ Download</button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        <div ref={end} />
      </div>
      <form className="flex gap-2 border-t border-slate-800 p-3"
        onSubmit={(e) => { e.preventDefault(); if (text.trim()) { launchGoal(sessionId, text.trim()); setText(""); } }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a follow-up…"
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm outline-none focus:border-af-medium" />
        <button className="rounded-lg bg-af-blue px-3 text-sm font-medium text-white hover:bg-af-blue-hover">Send</button>
      </form>
    </aside>
  );
}
