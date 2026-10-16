import { create } from "zustand";

export type AgentStatus =
  | "queued" | "thinking" | "running_tool" | "waiting_human"
  | "done" | "failed" | "paused" | "pruned";

export interface BanyanEvent {
  id: string;
  run_id: string;
  type: string;
  agent_id: string | null;
  parent_id: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

export interface AgentNode {
  id: string;
  parentId: string | null;
  depth: number;
  role: string;
  goal: string;
  status: AgentStatus;
  confidence: number | null;
  tokensUsed: number;
  result: string | null;
}

export interface Approval {
  id: string;
  agentId: string | null;
  kind: string;
  title: string;
  risk: "low" | "medium" | "high";
  details: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "edited";
}

interface BanyanState {
  seen: Set<string>;
  nodes: Record<string, AgentNode>;
  approvals: Record<string, Approval>;
  selectedId: string | null;
  select: (id: string | null) => void;
  runStatus: "idle" | "running" | "finished";
  applyEvent: (e: BanyanEvent) => void;
  reset: () => void;
}

// All UI state is derived from events, so replay on reconnect is free.
// Events are de-duplicated by id because the server replays history on every connect.
export const useBanyan = create<BanyanState>((set) => ({
  seen: new Set(),
  nodes: {},
  approvals: {},
  selectedId: null,
  select: (id) => set({ selectedId: id }),
  runStatus: "idle",
  reset: () => set({ seen: new Set(), nodes: {}, approvals: {}, selectedId: null, runStatus: "idle" }),
  applyEvent: (e) =>
    set((s) => {
      if (s.seen.has(e.id)) return s;
      const seen = new Set(s.seen).add(e.id);
      const p = e.payload;
      const nodes = { ...s.nodes };
      const approvals = { ...s.approvals };
      let runStatus = s.runStatus;

      switch (e.type) {
        case "run_started":
          runStatus = "running";
          break;
        case "run_finished":
          runStatus = "finished";
          break;
        case "agent_spawned":
          if (e.agent_id)
            nodes[e.agent_id] = {
              id: e.agent_id,
              parentId: e.parent_id,
              depth: (p.depth as number) ?? 0,
              role: (p.role as string) ?? "worker",
              goal: (p.goal as string) ?? "",
              status: (p.status as AgentStatus) ?? "queued",
              confidence: null,
              tokensUsed: 0,
              result: null,
            };
          break;
        case "agent_status":
          if (e.agent_id && nodes[e.agent_id])
            nodes[e.agent_id] = {
              ...nodes[e.agent_id],
              status: p.status as AgentStatus,
              goal: (p.goal as string) ?? nodes[e.agent_id].goal,
              tokensUsed: (p.tokens as number) ?? nodes[e.agent_id].tokensUsed,
            };
          break;
        case "needs_human": {
          const id = p.approval_id as string;
          approvals[id] = {
            id, agentId: e.agent_id, kind: p.kind as string, title: p.title as string,
            risk: (p.risk as Approval["risk"]) ?? "low",
            details: (p.details as Record<string, unknown>) ?? {}, status: "pending",
          };
          break;
        }
        case "human_decision": {
          const id = p.approval_id as string;
          if (approvals[id]) approvals[id] = { ...approvals[id], status: p.decision as Approval["status"] };
          break;
        }
        case "agent_finished":
          if (e.agent_id && nodes[e.agent_id])
            nodes[e.agent_id] = {
              ...nodes[e.agent_id],
              status: "done",
              result: (p.result as string) ?? null,
              confidence: (p.confidence as number) ?? null,
              tokensUsed: (p.tokens as number) ?? nodes[e.agent_id].tokensUsed,
            };
          break;
        case "agent_failed":
          if (e.agent_id && nodes[e.agent_id])
            nodes[e.agent_id] = {
              ...nodes[e.agent_id],
              status: "failed",
              result: (p.error as string) ?? null,
            };
          break;
      }
      return { seen, nodes, approvals, runStatus };
    }),
}));
