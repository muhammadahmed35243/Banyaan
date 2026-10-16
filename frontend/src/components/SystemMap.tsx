"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useBanyan } from "@/store/useBanyan";

/** Fixed components of the system. Particles travel the edges as events happen. */
const NODES: Record<string, { x: number; y: number; label: string; sub: string }> = {
  you: { x: 500, y: 60, label: "👤 You", sub: "approvals · controls" },
  phone: { x: 840, y: 60, label: "📱 Phone", sub: "ntfy push" },
  vault: { x: 160, y: 190, label: "🔐 Vault", sub: "encrypted secrets" },
  orchestrator: { x: 500, y: 190, label: "🌳 Orchestrator", sub: "plans · DAG · humans" },
  llm: { x: 840, y: 190, label: "🧠 LLM", sub: "Gemini / OpenAI" },
  tools: { x: 160, y: 330, label: "🧰 Tool Registry", sub: "built-in + grown" },
  agents: { x: 500, y: 330, label: "🤖 Agents", sub: "planner · workers · watchers" },
  inbox: { x: 840, y: 330, label: "📥 Email inbox", sub: "read-only" },
  sandbox: { x: 160, y: 470, label: "📦 Sandbox", sub: "isolated process" },
  serpapi: { x: 390, y: 480, label: "🔎 SerpAPI", sub: "web search" },
  web: { x: 610, y: 480, label: "🌐 Web", sub: "fetch_url" },
  db: { x: 840, y: 470, label: "🗄️ Database", sub: "events · bills" },
};

const EDGES: [string, string][] = [
  ["you", "orchestrator"], ["orchestrator", "agents"], ["agents", "llm"], ["agents", "serpapi"],
  ["agents", "web"], ["agents", "tools"], ["agents", "inbox"], ["tools", "sandbox"], ["agents", "sandbox"],
  ["vault", "agents"], ["agents", "you"], ["agents", "db"], ["agents", "phone"],
];

const W = 150;
const H = 54;

export default function SystemMap() {
  const flows = useBanyan((s) => s.flows);
  const counts = useBanyan((s) => s.edgeCounts);
  const [now, setNow] = useState(() => Date.now());

  // Re-render while particles are in flight so finished ones disappear.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const live = flows.filter((f) => now - f.at < 1300);
  const hot = new Set(live.flatMap((f) => [f.from, f.to]));
  const count = (a: string, b: string) => (counts[`${a}>${b}`] ?? 0) + (counts[`${b}>${a}`] ?? 0);
  const total = Object.values(counts).reduce((x, y) => x + y, 0);

  return (
    <div className="relative h-full w-full">
      <svg viewBox="0 0 1000 540" className="h-full w-full" preserveAspectRatio="xMidYMid meet">
        {EDGES.map(([a, b]) => {
          const n = count(a, b);
          const isHot = live.some((f) => (f.from === a && f.to === b) || (f.from === b && f.to === a));
          return (
            <g key={`${a}-${b}`}>
              <line x1={NODES[a].x} y1={NODES[a].y} x2={NODES[b].x} y2={NODES[b].y}
                stroke={isHot ? "#38bdf8" : n ? "#334155" : "#1e293b"} strokeWidth={isHot ? 3 : n ? 2 : 1}
                strokeDasharray={n ? undefined : "4 6"} style={{ transition: "stroke 0.3s" }} />
              {n > 0 && (
                <text x={(NODES[a].x + NODES[b].x) / 2 + 6} y={(NODES[a].y + NODES[b].y) / 2 - 4}
                  fill="#64748b" fontSize="11">{n}</text>
              )}
            </g>
          );
        })}
        {live.map((f) => {
          const a = NODES[f.from], b = NODES[f.to];
          if (!a || !b) return null;
          return (
            <motion.circle key={f.id} r={f.gold ? 7 : 5} fill={f.gold ? "#facc15" : "#38bdf8"}
              style={{ filter: `drop-shadow(0 0 6px ${f.gold ? "#facc15" : "#38bdf8"})` }}
              initial={{ cx: a.x, cy: a.y, opacity: 1 }} animate={{ cx: b.x, cy: b.y, opacity: [1, 1, 0.2] }}
              transition={{ duration: 1.1, ease: "easeInOut" }} />
          );
        })}
        {Object.entries(NODES).map(([id, n]) => (
          <g key={id} transform={`translate(${n.x - W / 2}, ${n.y - H / 2})`}>
            <rect width={W} height={H} rx={12}
              fill={hot.has(id) ? "#082f49" : "#0f172a"} stroke={hot.has(id) ? "#38bdf8" : "#334155"}
              strokeWidth={hot.has(id) ? 2.5 : 1.5} style={{ transition: "all 0.3s" }} />
            <text x={W / 2} y={23} textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight={600}>{n.label}</text>
            <text x={W / 2} y={41} textAnchor="middle" fill="#64748b" fontSize="10.5">{n.sub}</text>
          </g>
        ))}
      </svg>
      <div className="absolute bottom-3 left-4 text-xs text-slate-500">
        {total} messages so far · <span className="text-sky-400">●</span> data
        · <span className="text-yellow-400">●</span> secret used by a connector (never shown to the AI)
      </div>
    </div>
  );
}
