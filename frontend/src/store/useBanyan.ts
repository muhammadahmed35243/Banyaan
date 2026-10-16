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

interface BanyanState {
  seen: Set<string>;
  nodes: Record<string, AgentNode>;
  runStatus: "idle" | "running" | "finished";
  applyEvent: (e: BanyanEvent) => void;
  reset: () => void;
}

// All UI state is derived from events, so replay on reconnect is free.
// Events are de-duplicated by id because the server replays history on every connect.
export const useBanyan = create<BanyanState>((set) => ({
  seen: new Set(),
  nodes: {},
  runStatus: "idle",
  reset: () => set({ seen: new Set(), nodes: {}, runStatus: "idle" }),
  applyEvent: (e) =>
    set((s) => {
      if (s.seen.has(e.id)) return s;
      const seen = new Set(s.seen).add(e.id);
      const p = e.payload;
      const nodes = { ...s.nodes };
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
            nodes[e.agent_id] = { ...nodes[e.agent_id], status: p.status as AgentStatus };
          break;
        case "agent_finished":
          if (e.agent_id && nodes[e.agent_id])
            nodes[e.agent_id] = {
              ...nodes[e.agent_id],
              status: "done",
              result: (p.result as string) ?? null,
              confidence: (p.confidence as number) ?? null,
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
      return { seen, nodes, runStatus };
    }),
}));
