"use client";

import { useState } from "react";
import { useBanyan, type AgentStatus } from "@/store/useBanyan";

const COLOR: Record<AgentStatus, string> = {
  queued: "bg-slate-700", thinking: "bg-blue-500", running_tool: "bg-amber-500",
  waiting_human: "bg-purple-500", done: "bg-emerald-500", failed: "bg-red-500",
  paused: "bg-zinc-500", pruned: "bg-zinc-700", watching: "bg-cyan-500/70",
};
const TERMINAL: AgentStatus[] = ["done", "failed", "pruned"];
const fmt = (ms: number) => (ms < 60000 ? `${Math.round(ms / 1000)}s` : `${(ms / 60000).toFixed(1)}m`);

/** One row per agent on a shared time axis: overlapping bars = agents working in parallel. */
export default function Swimlanes() {
  const nodes = useBanyan((s) => s.nodes);
  const history = useBanyan((s) => s.history);
  const marks = useBanyan((s) => s.marks);
  const firstTs = useBanyan((s) => s.firstTs);
  const lastTs = useBanyan((s) => s.lastTs);
  const select = useBanyan((s) => s.select);
  const [humanOnly, setHumanOnly] = useState(false);
  const [recent, setRecent] = useState(false);

  if (firstTs === null || lastTs === null) {
    return <div className="grid h-full place-items-center text-sm text-slate-500">Run a goal to see the timeline.</div>;
  }
  const end = lastTs;
  const start = recent ? Math.max(firstTs, end - 120_000) : firstTs;
  const span = Math.max(1000, end - start);
  const x = (t: number) => `${Math.max(0, Math.min(100, ((t - start) / span) * 100))}%`;

  const lanes = Object.values(nodes)
    .filter((n) => !["alert", "action"].includes(n.role) && history[n.id]?.length)
    .filter((n) => !humanOnly || history[n.id].some((h) => h.status === "waiting_human"))
    .sort((a, b) => history[a.id][0].t - history[b.id][0].t);
  const parallel = (() => { // peak number of agents active at once
    const ev: [number, number][] = [];
    lanes.forEach((n) => {
      const h = history[n.id];
      const done = h.find((p) => TERMINAL.includes(p.status));
      ev.push([h[0].t, 1], [done ? done.t : end, -1]);
    });
    ev.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let cur = 0, peak = 0;
    ev.forEach(([, d]) => { cur += d; peak = Math.max(peak, cur); });
    return peak;
  })();

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 text-xs">
      <div className="mb-3 flex items-center gap-4 text-slate-400">
        <span>{lanes.length} agents · up to <b className="text-slate-200">{parallel} at once</b> · {fmt(end - firstTs)} total</span>
        <label className="flex items-center gap-1"><input type="checkbox" checked={humanOnly} onChange={(e) => setHumanOnly(e.target.checked)} /> human moments only</label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={recent} onChange={(e) => setRecent(e.target.checked)} /> last 2 min</label>
        <span className="ml-auto flex gap-3">
          {(["thinking", "running_tool", "waiting_human", "watching"] as AgentStatus[]).map((s) => (
            <span key={s} className="flex items-center gap-1"><i className={`inline-block h-2 w-3 rounded ${COLOR[s]}`} />{s.replace("_", " ")}</span>
          ))}
          <span>▲ tool · 🔔 alert</span>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        {lanes.map((n) => {
          const h = history[n.id];
          return (
            <div key={n.id} className="flex h-7 items-center border-b border-slate-900 hover:bg-slate-900/60"
              onClick={() => select(n.id)}>
              <div className="w-56 shrink-0 truncate pr-2 text-slate-400" title={n.goal}>
                <span className="text-slate-500">{n.role}</span> · {n.goal}
              </div>
              <div className="relative h-4 flex-1 rounded bg-slate-900">
                {h.map((p, i) => {
                  if (TERMINAL.includes(p.status)) return null;
                  const to = i + 1 < h.length ? h[i + 1].t : end;
                  if (to < start) return null;
                  return (
                    <div key={i} className={`absolute top-0 h-4 rounded-sm ${COLOR[p.status]}`}
                      title={`${p.status} · ${fmt(to - p.t)}`}
                      style={{ left: x(p.t), width: `calc(${x(to)} - ${x(p.t)} + 2px)` }} />
                  );
                })}
                {(marks[n.id] ?? []).filter((m) => m.t >= start).map((m, i) => (
                  <span key={i} title={m.label} className="absolute -top-0.5 text-[10px] leading-none"
                    style={{ left: x(m.t) }}>{m.kind === "alert" ? "🔔" : <b className="text-amber-300">▲</b>}</span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="ml-56 mt-1 flex justify-between text-slate-500">
        <span>{recent ? `-${fmt(end - start)}` : "0s"}</span><span>{fmt((end - start) / 2 + (start - firstTs))}</span><span>{fmt(end - firstTs)}</span>
      </div>
    </div>
  );
}
