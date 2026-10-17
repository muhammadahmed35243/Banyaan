"use client";

import { useEffect, useRef, useState } from "react";
import { launchGoal } from "@/lib/actions";
import { useBanyan } from "@/store/useBanyan";
import Markdown from "./Markdown";

const ACTIVE = ["queued", "thinking", "running_tool", "waiting_human", "paused"];

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

  return (
    <aside className="flex w-[34%] min-w-[22rem] max-w-[36rem] shrink-0 flex-col border-r border-slate-800">
      <h2 className="border-b border-slate-800 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        💬 Conversation
      </h2>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {list.length === 0 && (
          <p className="text-xs text-slate-500">Ask anything. Several goals can run at once; follow-ups remember this session.</p>
        )}
        {list.map((r) => {
          const mine = Object.values(nodes).filter((n) => n.id.startsWith(r.id));
          const working = mine.filter((n) => ACTIVE.includes(n.status));
          const waiting = mine.filter((n) => n.status === "waiting_human").length;
          const watcher = mine.find((n) => n.role === "watcher" && n.status === "watching");
          return (
            <div key={r.id} className="space-y-2">
              <div className="ml-10 rounded-2xl rounded-tr-sm bg-emerald-700/40 px-3 py-2 text-sm text-emerald-50">{r.goal}</div>
              <div className="mr-4 rounded-2xl rounded-tl-sm border border-slate-800 bg-slate-900 px-3 py-2">
                {r.result ? (
                  <Markdown text={r.result} />
                ) : r.status === "finished" ? (
                  <p className="text-sm text-red-300">This goal did not finish (a branch failed or was rejected). Click a red node for details.</p>
                ) : (
                  <div className="text-xs text-slate-400">
                    <span className="animate-pulse">●</span> {working.length} agent{working.length === 1 ? "" : "s"} working
                    {waiting > 0 && <span className="text-purple-300"> · {waiting} waiting for you →</span>}
                    <ul className="mt-1 space-y-0.5">
                      {working.slice(0, 6).map((n) => (
                        <li key={n.id} className="truncate"><span className="text-slate-500">{n.role}</span> · {n.goal}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {watcher && <p className="mt-1 text-xs text-cyan-300">👁 Watcher is still running for this goal.</p>}
                <button onClick={() => { setView("tree"); select(`${r.id}-root`); }}
                  className="mt-1 text-[10px] text-slate-500 hover:text-slate-300">
                  {mine.length} agents · show tree
                </button>
              </div>
            </div>
          );
        })}
        <div ref={end} />
      </div>
      <form className="flex gap-2 border-t border-slate-800 p-3"
        onSubmit={(e) => { e.preventDefault(); if (text.trim()) { launchGoal(sessionId, text.trim()); setText(""); } }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a follow-up…"
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm outline-none focus:border-emerald-500" />
        <button className="rounded-lg bg-emerald-600 px-3 text-sm hover:bg-emerald-500">Send</button>
      </form>
    </aside>
  );
}
