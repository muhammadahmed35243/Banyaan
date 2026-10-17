import { create } from "zustand";

export type AgentStatus =
  | "queued" | "thinking" | "running_tool" | "waiting_human"
  | "done" | "failed" | "paused" | "pruned" | "watching";

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
  dependsOn: string[]; // sibling agents whose results feed this one (e.g. researchers -> analyst)
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

export interface Alert {
  id: string;
  ts: string;
  agentId: string | null;
  sender: string;
  subject: string;
  summary: string;
  amount: string | null;
}

export interface Run {
  id: string; goal: string; status: "running" | "finished"; result: string | null; startedAt: number;
}

export interface Bill {
  id: string; payee: string; amount: string; dueDate: string | null; status: "due" | "paid"; subject: string;
}

/** A particle on the System Map: a message moving between two components. */
export interface Flow { id: string; from: string; to: string; at: number; gold: boolean }

/** Timeline data per agent: status changes and point marks (tool calls, alerts). */
export interface StatusPoint { status: AgentStatus; t: number }
export interface Mark { t: number; kind: "tool" | "alert"; label: string }

const TOOL_TARGET: Record<string, string> = {
  web_search: "serpapi", fetch_url: "web", email_inbox: "inbox",
  calculate: "tools", current_time: "tools", send_email: "tools",
};

/** Which System Map edges an event travels along. Derived from ordinary events, so the
 * map needs no extra backend support and replays like everything else. */
function flowsFor(e: BanyanEvent): [string, string, boolean][] {
  const p = e.payload;
  switch (e.type) {
    case "run_started": return [["you", "orchestrator", false]];
    case "run_finished": return [["orchestrator", "you", false]];
    case "agent_spawned": return [["orchestrator", "agents", false]];
    case "agent_status": return p.tokens !== undefined ? [["agents", "llm", false]] : [];
    case "tool_call": {
      const t = TOOL_TARGET[p.tool as string];
      return t ? [["agents", t, false]] : [["tools", "sandbox", false]]; // a grown tool runs in the sandbox
    }
    case "toolsmith_stage": return [["agents", "sandbox", false]];
    case "tool_loaded": return [["sandbox", "tools", false]];
    case "secret_used": return [["vault", "agents", true]];
    case "needs_human": return [["orchestrator", "you", false]];
    case "human_decision": return [["you", "orchestrator", false]];
    case "alert": return [["agents", "you", false]];
    case "bill_tracked": return [["agents", "db", false]];
    case "notified": return [["agents", "phone", false]];
    default: return [];
  }
}

interface BanyanState {
  seen: Set<string>;
  nodes: Record<string, AgentNode>;
  approvals: Record<string, Approval>;
  runs: Record<string, Run>;
  alerts: Alert[];
  dismissed: Set<string>;
  bills: Bill[];
  flows: Flow[];
  edgeCounts: Record<string, number>;
  history: Record<string, StatusPoint[]>;
  marks: Record<string, Mark[]>;
  firstTs: number | null;
  lastTs: number | null;
  live: boolean; // false while the first poll replays history (no particles for old events)
  selectedId: string | null;
  toolsLoaded: number;
  view: "tree" | "map" | "timeline";
  setView: (v: "tree" | "map" | "timeline") => void;
  select: (id: string | null) => void;
  dismiss: (id: string) => void;
  setLive: () => void;
  applyEvent: (e: BanyanEvent) => void;
  reset: () => void;
}

const EMPTY = {
  seen: new Set<string>(), nodes: {}, approvals: {}, runs: {}, alerts: [], dismissed: new Set<string>(),
  bills: [], flows: [], edgeCounts: {}, history: {}, marks: {}, firstTs: null, lastTs: null, live: false,
  selectedId: null, toolsLoaded: 0,
};

// All UI state is derived from events, so replay on reconnect is free.
// Events are de-duplicated by id because the first poll replays the whole session.
// One session holds many runs (goals) side by side; agent ids are unique across runs.
export const useBanyan = create<BanyanState>((set) => ({
  ...EMPTY,
  view: "tree",
  setView: (view) => set({ view }),
  select: (id) => set({ selectedId: id }),
  dismiss: (id) => set((s) => ({ dismissed: new Set(s.dismissed).add(id) })),
  setLive: () => set({ live: true }),
  reset: () => set({ ...EMPTY, seen: new Set(), dismissed: new Set() }),
  applyEvent: (e) =>
    set((s) => {
      if (s.seen.has(e.id)) return s;
      const seen = new Set(s.seen).add(e.id);
      const p = e.payload;
      const nodes = { ...s.nodes };
      const approvals = { ...s.approvals };
      const runs = { ...s.runs };
      let alerts = s.alerts;
      let bills = s.bills;
      let toolsLoaded = s.toolsLoaded;
      const t = Date.parse(e.ts);
      const firstTs = s.firstTs === null ? t : Math.min(s.firstTs, t);
      const lastTs = s.lastTs === null ? t : Math.max(s.lastTs, t);

      // System Map: count every hop; animate only live ones.
      const hops = flowsFor(e);
      let { flows, edgeCounts, history, marks } = s;
      if (hops.length) {
        edgeCounts = { ...edgeCounts };
        hops.forEach(([a, b]) => { edgeCounts[`${a}>${b}`] = (edgeCounts[`${a}>${b}`] ?? 0) + 1; });
        if (s.live) {
          const now = Date.now();
          flows = [...flows.filter((f) => now - f.at < 2000),
            ...hops.map(([from, to, gold], i) => ({ id: `${e.id}-${i}`, from, to, at: now, gold }))].slice(-60);
        }
      }
      // Timeline: status changes and marks per agent.
      if (e.agent_id && (e.type === "agent_spawned" || e.type === "agent_status" || e.type === "agent_finished"
        || e.type === "agent_failed")) {
        const st = (e.type === "agent_finished" ? "done" : e.type === "agent_failed" ? "failed"
          : (p.status as AgentStatus) ?? "queued") as AgentStatus;
        const h = history[e.agent_id] ?? [];
        if (h[h.length - 1]?.status !== st) history = { ...history, [e.agent_id]: [...h, { status: st, t }] };
      }
      if (e.agent_id && (e.type === "tool_call" || e.type === "alert")) {
        const label = e.type === "alert" ? String(p.subject ?? "alert") : String(p.tool ?? "tool");
        marks = { ...marks, [e.agent_id]: [...(marks[e.agent_id] ?? []), { t, kind: e.type === "alert" ? "alert" : "tool", label }] };
      }

      switch (e.type) {
        case "bill_tracked":
          bills = [...bills, {
            id: p.bill_id as string, payee: (p.payee as string) ?? "", amount: (p.amount as string) ?? "",
            dueDate: (p.due_date as string) ?? null, status: (p.status as Bill["status"]) ?? "due",
            subject: (p.subject as string) ?? "",
          }];
          break;
        case "run_started":
          runs[e.run_id] = { id: e.run_id, goal: (p.goal as string) ?? "", status: "running", result: null, startedAt: t };
          break;
        case "run_finished":
          runs[e.run_id] = {
            ...(runs[e.run_id] ?? { id: e.run_id, goal: "", startedAt: t }),
            status: "finished", result: (p.result as string) ?? null,
          };
          break;
        case "tool_loaded":
          toolsLoaded += 1;
          break;
        case "alert":
          alerts = [{
            id: (p.alert_id as string) ?? e.id, ts: e.ts, agentId: e.agent_id,
            sender: (p.sender as string) ?? "", subject: (p.subject as string) ?? "",
            summary: (p.summary as string) ?? "", amount: (p.amount as string) ?? null,
          }, ...alerts];
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
              dependsOn: (p.depends_on as string[]) ?? [],
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
      return { seen, nodes, approvals, runs, alerts, bills, toolsLoaded, flows, edgeCounts, history, marks,
        firstTs, lastTs };
    }),
}));
