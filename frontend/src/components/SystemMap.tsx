"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useBanyan } from "@/store/useBanyan";

/** The parts of the system. Messages travel the edges as events happen; hover a part to see its
 * links, click it for what went through it, drag it to rearrange the map. */
interface Part { x: number; y: number; icon: string; label: string; sub: string; about: string }

const PARTS: Record<string, Part> = {
  you: { x: 500, y: 70, icon: "👤", label: "You", sub: "approvals · controls",
    about: "Every new tool, secret, risky action and low-confidence answer stops here for your decision." },
  phone: { x: 850, y: 70, icon: "📱", label: "Phone", sub: "ntfy push", about: "Watcher alerts pushed to your phone, even with the tab closed." },
  vault: { x: 150, y: 200, icon: "🔐", label: "Vault", sub: "encrypted secrets",
    about: "Fernet-encrypted credentials. Connectors read them on the server; the AI never sees a value." },
  orchestrator: { x: 500, y: 200, icon: "🌳", label: "Orchestrator", sub: "plans · DAG · humans",
    about: "Plans each goal into parallel agents, enforces budgets and waits for humans where needed." },
  llm: { x: 850, y: 200, icon: "🧠", label: "LLM", sub: "Gemini / OpenAI", about: "Every reasoning step of every agent." },
  tools: { x: 150, y: 335, icon: "🧰", label: "Tool Registry", sub: "built-in + grown", about: "Built-in tools plus tools grown by the Toolsmith and approved by you." },
  agents: { x: 500, y: 335, icon: "🤖", label: "Agents", sub: "planner · workers · watchers", about: "The team working on your goals, side by side." },
  inbox: { x: 850, y: 335, icon: "📥", label: "Email inbox", sub: "read-only", about: "Watchers read new mail here (Gmail, IMAP or the demo inbox)." },
  services: { x: 850, y: 470, icon: "🔌", label: "Your services", sub: "Classroom · Shopify",
    about: "Your connected accounts, called through one gateway that adds your credential on the server." },
  sandbox: { x: 150, y: 470, icon: "📦", label: "Sandbox", sub: "isolated process", about: "Where grown tools are built and tested before you approve them." },
  serpapi: { x: 390, y: 490, icon: "🔎", label: "Search", sub: "web + images", about: "Web and image search for researchers." },
  web: { x: 610, y: 490, icon: "🌐", label: "Web", sub: "fetch_url", about: "Pages agents read for details and prices." },
  db: { x: 500, y: 610, icon: "🗄️", label: "Database", sub: "events · bills · memory", about: "Every event (so sessions replay), the bills tracker and session memory." },
};

const EDGES: [string, string][] = [
  ["you", "orchestrator"], ["orchestrator", "agents"], ["agents", "llm"], ["agents", "serpapi"],
  ["agents", "web"], ["agents", "tools"], ["agents", "inbox"], ["tools", "sandbox"], ["agents", "sandbox"],
  ["vault", "agents"], ["agents", "you"], ["agents", "db"], ["agents", "phone"], ["agents", "services"],
];

const W = 168;
const H = 62;
const VIEW = { w: 1000, h: 670 };

export default function SystemMap() {
  const flows = useBanyan((s) => s.flows);
  const counts = useBanyan((s) => s.edgeCounts);
  const trail = useBanyan((s) => s.trail);
  const [now, setNow] = useState(() => Date.now());
  const [pos, setPos] = useState(() => Object.fromEntries(Object.entries(PARTS).map(([k, p]) => [k, { x: p.x, y: p.y }])));
  const [hover, setHover] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const drag = useRef<{ id: string; dx: number; dy: number; moved: boolean } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  // Re-render while particles are in flight so finished ones disappear.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const live = flows.filter((f) => now - f.at < 1300);
  const hot = new Set(live.flatMap((f) => [f.from, f.to]));
  const count = (a: string, b: string) => (counts[`${a}>${b}`] ?? 0) + (counts[`${b}>${a}`] ?? 0);
  const total = Object.values(counts).reduce((x, y) => x + y, 0);
  const focus = hover ?? picked;
  const linked = (a: string, b: string) => EDGES.some(([x, y]) => (x === a && y === b) || (x === b && y === a));
  const touches = (id: string) => EDGES.filter(([a, b]) => a === id || b === id).reduce((n, [a, b]) => n + count(a, b), 0);

  // Screen -> SVG coordinates (the SVG keeps its aspect ratio, centred).
  const toSvg = (e: React.PointerEvent) => {
    const r = svg.current!.getBoundingClientRect();
    const k = Math.max(VIEW.w / r.width, VIEW.h / r.height);
    const ox = (r.width * k - VIEW.w) / 2, oy = (r.height * k - VIEW.h) / 2;
    return { x: (e.clientX - r.left) * k - ox, y: (e.clientY - r.top) * k - oy };
  };

  const activity = useMemo(() => (picked ? trail.filter((h) => h.from === picked || h.to === picked).slice(-12).reverse() : []),
    [picked, trail]);

  return (
    <div className="relative h-full w-full select-none bg-slate-950">
      <svg ref={svg} viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} className="h-full w-full" preserveAspectRatio="xMidYMid meet"
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const p = toSvg(e);
          d.moved = true;
          setPos((s) => ({ ...s, [d.id]: {
            x: Math.max(W / 2, Math.min(VIEW.w - W / 2, p.x - d.dx)), y: Math.max(H / 2, Math.min(VIEW.h - H / 2, p.y - d.dy)) } }));
        }}
        onPointerUp={() => { setTimeout(() => { drag.current = null; }, 0); }}
        onPointerLeave={() => { drag.current = null; }}
        onClick={(e) => { if (e.target === svg.current) setPicked(null); }}>
        <defs>
          <filter id="glow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.2" fill="#d3d9e8" /></pattern>
        </defs>
        <rect width={VIEW.w} height={VIEW.h} fill="url(#dots)" />

        {EDGES.map(([a, b]) => {
          const n = count(a, b);
          const isHot = live.some((f) => (f.from === a && f.to === b) || (f.from === b && f.to === a));
          const lit = !!focus && (a === focus || b === focus);
          const dim = !!focus && !lit;
          const A = pos[a], B = pos[b];
          return (
            <g key={`${a}-${b}`} style={{ opacity: dim ? 0.15 : 1, transition: "opacity 0.25s" }}>
              <line x1={A.x} y1={A.y} x2={B.x} y2={B.y}
                stroke={isHot || lit ? "#000aff" : n ? "#a8b2d1" : "#d5dbe7"} strokeWidth={isHot ? 3 : lit ? 2.5 : n ? 1.8 : 1.2}
                strokeDasharray={n ? undefined : "5 6"} style={{ transition: "stroke 0.3s, stroke-width 0.3s" }} />
              {n > 0 && (
                <g transform={`translate(${(A.x + B.x) / 2}, ${(A.y + B.y) / 2})`}>
                  <rect x={-15} y={-10} width={30} height={18} rx={9} fill={lit ? "#000aff" : "#ffffff"} stroke={lit ? "#000aff" : "#d5dbe7"} />
                  <text textAnchor="middle" y={3} fontSize="10.5" fontWeight={600} fill={lit ? "#ffffff" : "#374151"}>{n}</text>
                </g>
              )}
            </g>
          );
        })}

        {live.map((f) => {
          const a = pos[f.from], b = pos[f.to];
          if (!a || !b) return null;
          const c = f.gold ? "#f59e0b" : "#000aff";
          return (
            <motion.circle key={f.id} r={f.gold ? 7 : 5.5} fill={c} filter="url(#glow)"
              initial={{ cx: a.x, cy: a.y, opacity: 1 }} animate={{ cx: b.x, cy: b.y, opacity: [1, 1, 0.3] }}
              transition={{ duration: 1.1, ease: "easeInOut" }} />
          );
        })}

        {Object.entries(PARTS).map(([id, p]) => {
          const { x, y } = pos[id];
          const isHot = hot.has(id);
          const dim = !!focus && focus !== id && !linked(focus, id);
          const n = touches(id);
          const on = picked === id;
          return (
            <g key={id} transform={`translate(${x - W / 2}, ${y - H / 2})`}
              style={{ cursor: "grab", opacity: dim ? 0.35 : 1, transition: "opacity 0.25s" }}
              onPointerEnter={() => setHover(id)} onPointerLeave={() => setHover(null)}
              onPointerDown={(e) => { const q = toSvg(e); drag.current = { id, dx: q.x - x, dy: q.y - y, moved: false }; }}
              onClick={() => { if (!drag.current?.moved) setPicked((c) => (c === id ? null : id)); }}>
              {isHot && (
                <motion.rect width={W} height={H} rx={14} fill="none" stroke="#000aff" strokeWidth={2}
                  initial={{ opacity: 0.8, scale: 1 }} animate={{ opacity: 0, scale: 1.15 }} transition={{ duration: 0.9 }}
                  style={{ transformOrigin: `${W / 2}px ${H / 2}px` }} />
              )}
              <rect width={W} height={H} rx={14} fill={on ? "#e8ebff" : "#ffffff"}
                stroke={on || isHot ? "#000aff" : hover === id ? "#7c8cff" : "#d5dbe7"} strokeWidth={on || isHot ? 2 : 1.2}
                style={{ filter: "drop-shadow(0 2px 6px rgba(16,24,40,0.08))", transition: "all 0.25s" }} />
              <text x={14} y={39} fontSize="22">{p.icon}</text>
              <text x={48} y={28} fill="#111827" fontSize="14" fontWeight={600}>{p.label}</text>
              <text x={48} y={46} fill="#6b7280" fontSize="10.5">{p.sub}</text>
              {n > 0 && (
                <g transform={`translate(${W - 6}, 6)`}>
                  <circle r={11} fill="#000aff" />
                  <text textAnchor="middle" y={4} fontSize="9.5" fontWeight={700} fill="#fff">{n > 999 ? "1k+" : n}</text>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      <AnimatePresence>
        {hover && !picked && (
          <motion.div key={hover} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="shadow-card pointer-events-none absolute left-4 top-4 max-w-xs rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs">
            <div className="font-semibold text-slate-100">{PARTS[hover].icon} {PARTS[hover].label}</div>
            <div className="mt-0.5 text-slate-400">{PARTS[hover].about}</div>
            <div className="mt-1 font-medium text-af-blue">{touches(hover)} messages · click for activity</div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {picked && (
          <motion.aside key={picked} initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
            className="shadow-card absolute bottom-3 right-3 top-3 w-72 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3 text-xs">
            <div className="flex items-start justify-between">
              <div className="text-sm font-semibold text-slate-100">{PARTS[picked].icon} {PARTS[picked].label}</div>
              <button onClick={() => setPicked(null)} className="text-slate-500 hover:text-slate-200">✕</button>
            </div>
            <p className="mt-1 text-slate-400">{PARTS[picked].about}</p>
            <div className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Links</div>
            <ul className="mt-1 space-y-1">
              {EDGES.filter(([a, b]) => a === picked || b === picked).map(([a, b]) => {
                const other = a === picked ? b : a;
                return (
                  <li key={other} className="flex items-center justify-between rounded-lg bg-slate-950 px-2 py-1">
                    <button onClick={() => setPicked(other)} className="text-slate-200 hover:text-af-blue">
                      {PARTS[other].icon} {PARTS[other].label}
                    </button>
                    <span className="font-mono text-slate-500">{count(a, b)}</span>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Recent activity</div>
            {activity.length === 0 ? (
              <p className="mt-1 text-slate-500">Nothing yet in this session.</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {activity.map((h) => (
                  <motion.li key={h.id} initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }}
                    className="rounded-lg border-l-2 bg-slate-950 px-2 py-1" style={{ borderColor: h.gold ? "#f59e0b" : "#000aff" }}>
                    <div className="text-slate-200">{h.label}</div>
                    <div className="text-[10px] text-slate-500">
                      {PARTS[h.from]?.label} → {PARTS[h.to]?.label} · {new Date(h.t).toLocaleTimeString()}
                    </div>
                  </motion.li>
                ))}
              </ul>
            )}
          </motion.aside>
        )}
      </AnimatePresence>

      <div className="pointer-events-none absolute right-4 top-3 flex flex-col items-end gap-0.5 text-[11px] text-slate-500">
        <span className="font-medium text-slate-300">{total} messages so far</span>
        <span><span className="text-af-blue">●</span> data</span>
        <span><span className="text-amber-500">●</span> secret used by a connector (never shown to the AI)</span>
        <span className="text-slate-600">Hover · click · drag the boxes</span>
      </div>
    </div>
  );
}
