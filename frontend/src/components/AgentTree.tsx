"use client";

import { useEffect, useMemo } from "react";
import {
  Background, Handle, Position, ReactFlow, ReactFlowProvider, useReactFlow,
  type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { motion } from "framer-motion";
import "@xyflow/react/dist/style.css";
import { useBanyan, type AgentNode, type AgentStatus } from "@/store/useBanyan";

const W = 220;
const H = 84;

const STATUS_STYLE: Record<AgentStatus, string> = {
  queued: "border-slate-600 bg-slate-900/80",
  thinking: "border-blue-500 bg-blue-950/70",
  running_tool: "border-amber-500 bg-amber-950/60",
  waiting_human: "border-purple-500 bg-purple-950/70 pulse-human",
  done: "border-emerald-500 bg-emerald-950/60",
  failed: "border-red-500 bg-red-950/60",
  paused: "border-zinc-500 bg-zinc-800/70",
  pruned: "border-zinc-700 bg-zinc-900/40 opacity-40",
  watching: "border-cyan-400 bg-cyan-950/60 pulse-watch",
};

const ROLE_LABEL: Record<string, string> = {
  builder: "🔧 builder", tester: "🔧 tester", critic: "🔧 critic", watcher: "👁 watcher", alert: "🔔 alert",
};

function AgentCard({ data }: NodeProps<Node<{ agent: AgentNode }>>) {
  const a = data.agent;
  return (
    <motion.div
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      style={{ width: W, height: H }}
      className={`cursor-pointer rounded-xl border-2 px-3 py-2 text-xs transition-colors duration-500 ${STATUS_STYLE[a.status]}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-500" />
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wide text-slate-400">
        <span className={["builder", "tester", "critic"].includes(a.role) ? "text-purple-300"
          : ["watcher", "alert"].includes(a.role) ? "text-cyan-300" : ""}>
          {ROLE_LABEL[a.role] ?? a.role}
        </span>
        <span>{a.status.replace("_", " ")}</span>
      </div>
      <div className="mt-1 line-clamp-2 text-sm leading-tight text-slate-100">{a.goal}</div>
      {a.tokensUsed > 0 && <div className="text-[10px] text-slate-500">{a.tokensUsed} tokens</div>}
      {a.confidence !== null && (
        <div className="mt-1.5 h-1 rounded bg-slate-700">
          <div className="h-1 rounded bg-emerald-400" style={{ width: `${a.confidence * 100}%` }} />
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-slate-500" />
    </motion.div>
  );
}

const nodeTypes = { agent: AgentCard };

function layout(agents: AgentNode[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 30, ranksep: 70 });
  g.setDefaultEdgeLabel(() => ({}));
  const ids = new Set(agents.map((a) => a.id));
  agents.forEach((a) => g.setNode(a.id, { width: W, height: H }));
  const edges: Edge[] = [];
  agents.forEach((a) => {
    if (a.parentId && ids.has(a.parentId)) {
      g.setEdge(a.parentId, a.id);
      edges.push({ id: `${a.parentId}-${a.id}`, source: a.parentId, target: a.id, animated: true,
        style: { stroke: "#475569" } });
    }
  });
  dagre.layout(g);
  const nodes: Node[] = agents.map((a) => {
    const p = g.node(a.id);
    return { id: a.id, type: "agent", position: { x: p.x - W / 2, y: p.y - H / 2 }, data: { agent: a } };
  });
  return { nodes, edges };
}

function Tree() {
  const agentMap = useBanyan((s) => s.nodes);
  const { nodes, edges } = useMemo(() => layout(Object.values(agentMap)), [agentMap]);
  const { fitView } = useReactFlow();
  const count = nodes.length;
  // Re-fit when the tree grows; fitView's prop only applies on first render.
  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.3, duration: 400 }), 50);
    return () => clearTimeout(t);
  }, [count, fitView]);
  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.3 }}
      onNodeClick={(_, n) => useBanyan.getState().select(n.id)}
      nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode="dark">
      <Background color="#1e293b" gap={24} />
    </ReactFlow>
  );
}

export default function AgentTree() {
  return (
    <ReactFlowProvider>
      <Tree />
    </ReactFlowProvider>
  );
}
