"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  Background, BackgroundVariant, BaseEdge, Controls, Handle, Position, ReactFlow, ReactFlowProvider,
  getBezierPath, useReactFlow, type Edge, type EdgeProps, type Node, type NodeProps,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { motion } from "framer-motion";
import "@xyflow/react/dist/style.css";
import { useBanyan, type AgentNode, type AgentStatus } from "@/store/useBanyan";

const W = 220;
const H = 84;

/** Per status: accent colour (left bar + border), pill style, and the card's motion class. */
const STATUS: Record<AgentStatus, { accent: string; pill: string; card?: string; label: string }> = {
  queued: { accent: "#9aa3b5", pill: "bg-slate-800 text-slate-400", label: "queued" },
  thinking: { accent: "#000aff", pill: "bg-af-soft text-af-blue", card: "agent-thinking", label: "thinking" },
  running_tool: { accent: "#2563eb", pill: "bg-blue-100 text-blue-700", card: "agent-thinking", label: "using tool" },
  waiting_human: { accent: "#7c3aed", pill: "bg-purple-100 text-purple-700", card: "pulse-human", label: "needs you" },
  done: { accent: "#10b981", pill: "bg-emerald-50 text-emerald-700", label: "done" },
  failed: { accent: "#dc2626", pill: "bg-red-50 text-red-700", label: "failed" },
  paused: { accent: "#9aa3b5", pill: "bg-slate-800 text-slate-500", label: "paused" },
  pruned: { accent: "#d5dbe7", pill: "bg-slate-800 text-slate-500", card: "opacity-50", label: "pruned" },
  watching: { accent: "#0e7490", pill: "bg-cyan-50 text-cyan-700", card: "pulse-watch", label: "watching" },
};

const ROLE_LABEL: Record<string, string> = {
  planner: "Planner", researcher: "Researcher", analyst: "Analyst", writer: "Writer", worker: "Worker",
  builder: "🔧 Builder", tester: "🔧 Tester", critic: "🔧 Critic", watcher: "👁 Watcher", alert: "🔔 Alert",
  action: "✓ Action",
};

function StatusIcon({ s }: { s: AgentStatus }) {
  if (s === "thinking" || s === "running_tool") return <span className="agent-spinner" />;
  if (s === "done")
    return (
      <motion.span initial={{ scale: 0 }} animate={{ scale: [0, 1.4, 1] }} transition={{ duration: 0.45 }}
        className="inline-block">✓</motion.span>
    );
  return <span>{s === "failed" ? "!" : s === "paused" ? "⏸" : s === "waiting_human" ? "✋" : s === "watching" ? "👁" : "•"}</span>;
}

function AgentCard({ data, selected }: NodeProps<Node<{ agent: AgentNode }>>) {
  const a = data.agent;
  const st = STATUS[a.status] ?? STATUS.queued;
  return (
    <motion.div
      initial={{ scale: 0.5, opacity: 0, y: -12 }}
      animate={{ scale: 1, opacity: 1, y: 0 }}
      whileHover={{ y: -2, boxShadow: "0 10px 24px rgba(0, 10, 255, 0.12)" }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      style={{ width: W, height: H, borderColor: selected ? "#000aff" : st.accent + "55" }}
      className={`shadow-card relative cursor-pointer overflow-hidden rounded-xl border bg-white py-2 pl-4 pr-3 text-xs ${st.card ?? ""} ${selected ? "ring-2 ring-af-blue/40" : ""}`}
    >
      {/* Status accent bar; its colour animates as the agent moves through states. */}
      <motion.span className="absolute inset-y-0 left-0 w-1.5" animate={{ backgroundColor: st.accent }} transition={{ duration: 0.5 }} />
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-600" />
      <div className="flex items-center justify-between gap-2 text-[10px] font-medium">
        <span className={`uppercase tracking-wide ${["watcher", "alert"].includes(a.role) ? "text-cyan-700"
          : ["builder", "tester", "critic"].includes(a.role) ? "text-purple-700" : "text-slate-500"}`}>
          {ROLE_LABEL[a.role] ?? a.role}
        </span>
        <motion.span key={a.status} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
          className={`flex items-center gap-1 rounded-full px-2 py-0.5 ${st.pill}`}>
          <StatusIcon s={a.status} /> {st.label}
        </motion.span>
      </div>
      <div className="mt-1 line-clamp-2 text-[13px] font-medium leading-tight text-slate-100">{a.goal}</div>
      <div className="mt-1 flex items-center gap-2">
        {a.tokensUsed > 0 && <span className="text-[10px] text-slate-500">{a.tokensUsed.toLocaleString()} tokens</span>}
        {a.confidence !== null && (
          <div className="h-1 flex-1 overflow-hidden rounded bg-slate-800">
            <motion.div className="h-1 rounded bg-af-blue" initial={{ width: 0 }}
              animate={{ width: `${a.confidence * 100}%` }} transition={{ duration: 0.8, ease: "easeOut" }} />
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-600" />
    </motion.div>
  );
}

const ACTIVE: AgentStatus[] = ["queued", "thinking", "running_tool"];

/** An edge that carries a moving pulse while the agent at its end is working. */
function LiveEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, label,
  labelStyle, labelBgStyle, data }: EdgeProps<Edge<{ live?: boolean; feeds?: boolean }>>) {
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const live = !!data?.live;
  return (
    <>
      <BaseEdge id={id} path={path} label={label} labelX={lx} labelY={ly} labelStyle={labelStyle}
        labelBgStyle={labelBgStyle} labelBgPadding={[4, 2]} labelBgBorderRadius={4}
        style={{ ...style, stroke: live ? "#000aff" : style?.stroke, strokeWidth: live ? 2.2 : 1.5,
          transition: "stroke 0.4s" }} />
      {live && (
        <circle r={4} fill="#000aff" style={{ filter: "drop-shadow(0 0 4px rgba(0,10,255,0.6))" }}>
          <animateMotion dur="1.4s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </>
  );
}

const nodeTypes = { agent: AgentCard };
const edgeTypes = { live: LiveEdge };

/** Each goal's tree is laid out on its own and placed left to right in launch order, so
 * trees never swap places as they grow (one dagre graph would reshuffle them). */
function layout(agents: AgentNode[]): { nodes: Node[]; edges: Edge[] } {
  const byId = new Map(agents.map((a) => [a.id, a]));
  const rootOf = (a: AgentNode): string => {
    let cur = a;
    while (cur.parentId && byId.has(cur.parentId)) cur = byId.get(cur.parentId)!;
    return cur.id;
  };
  const groups = new Map<string, AgentNode[]>(); // insertion order = launch order
  agents.forEach((a) => {
    const r = rootOf(a);
    groups.set(r, [...(groups.get(r) ?? []), a]);
  });

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let offsetX = 0;
  groups.forEach((members) => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "TB", nodesep: 30, ranksep: 70 });
    g.setDefaultEdgeLabel(() => ({}));
    members.forEach((a) => g.setNode(a.id, { width: W, height: H }));
    members.forEach((a) => {
      const deps = a.dependsOn.filter((d) => byId.has(d));
      // An agent that waits for siblings sits below them, with "feeds" arrows showing the hand-off.
      if (a.parentId && byId.has(a.parentId) && deps.length === 0) {
        g.setEdge(a.parentId, a.id);
        edges.push({ id: `${a.parentId}-${a.id}`, source: a.parentId, target: a.id, type: "live",
          data: { live: ACTIVE.includes(a.status) }, style: { stroke: "#c3cbe0" } });
      }
      deps.forEach((d) => {
        g.setEdge(d, a.id);
        edges.push({ id: `${d}>${a.id}`, source: d, target: a.id, type: "live", label: "feeds",
          data: { live: ACTIVE.includes(a.status), feeds: true },
          labelStyle: { fill: "#0000af", fontSize: 10, fontWeight: 600 }, labelBgStyle: { fill: "#e8ebff" },
          style: { stroke: "#7c8cff", strokeDasharray: "6 4" } });
      });
    });
    dagre.layout(g);
    let maxX = 0;
    members.forEach((a) => {
      const p = g.node(a.id);
      maxX = Math.max(maxX, p.x + W / 2);
      nodes.push({ id: a.id, type: "agent", position: { x: offsetX + p.x - W / 2, y: p.y - H / 2 }, data: { agent: a } });
    });
    offsetX += maxX + 90;
  });
  return { nodes, edges };
}

function Tree() {
  const agentMap = useBanyan((s) => s.nodes);
  const { nodes, edges } = useMemo(() => layout(Object.values(agentMap)), [agentMap]);
  const { fitView } = useReactFlow();
  const box = useRef<HTMLDivElement>(null);
  const count = nodes.length;
  // Re-fit when the tree grows; fitView's prop only applies on first render.
  useEffect(() => {
    // Twice: once right away, once after React Flow has measured the new nodes.
    const fit = () => fitView({ padding: 0.2, duration: 400 });
    const a = setTimeout(fit, 50);
    const b = setTimeout(fit, 500);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [count, fitView]);
  // ...and whenever its own area changes size (e.g. the approval inbox widens), not only the window.
  useEffect(() => {
    if (!box.current) return;
    let t: ReturnType<typeof setTimeout>;
    const ro = new ResizeObserver(() => { clearTimeout(t); t = setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 120); });
    ro.observe(box.current);
    return () => { clearTimeout(t); ro.disconnect(); };
  }, [count > 0, fitView]); // eslint-disable-line react-hooks/exhaustive-deps
  if (count === 0) {
    return (
      <div className="grid h-full place-items-center text-center">
        <div>
          <motion.div className="text-5xl" animate={{ y: [0, -6, 0] }} transition={{ duration: 3, repeat: Infinity }}>🌳</motion.div>
          <p className="mt-3 text-sm text-slate-300">Give Banyan a goal, or press <b>▶ Demo</b>.</p>
          <p className="mt-1 text-xs text-slate-500">
            Try: “Any time I get an email about a payment, tell me” · “Compare MacBook Air prices at 3 stores”
          </p>
          <p className="mt-1 text-xs text-slate-500">Click 🎙 to talk to it. Every new tool, secret and risky action waits for you.</p>
        </div>
      </div>
    );
  }
  return (
    <div ref={box} className="h-full w-full">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView
        fitViewOptions={{ padding: 0.3 }} minZoom={0.15} onNodeClick={(_, n) => useBanyan.getState().select(n.id)}
        onPaneClick={() => useBanyan.getState().select(null)}
        nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode="light">
        <Background variant={BackgroundVariant.Dots} color="#c9d1e3" gap={22} size={1.4} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}

export default function AgentTree() {
  return (
    <ReactFlowProvider>
      <Tree />
    </ReactFlowProvider>
  );
}
