import { API_URL } from "./config";
import { newId } from "./ids";

/** Shared by buttons and voice commands, so voice never gets more power than a click. */

const post = (path: string, body?: object) =>
  fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

/** Each goal is a new run in the session. The backend runs it inside this one request
 * (serverless has no background tasks) while the page polls the session. */
export function launchGoal(sessionId: string, goal: string) {
  const runId = newId();
  post("/api/goals", { goal, run_id: runId, session_id: sessionId })
    .catch((err) => console.error("Could not reach backend", err));
  return runId;
}

export function launchFakeRun(sessionId: string) {
  post(`/api/debug/fake_run/${newId()}?session_id=${sessionId}`).catch(console.error);
}

export const DEMO_GOALS = [
  "Any time I get an email related to payment, tell me",
  "Compare the price of a MacBook Air at Daraz, PriceOye and Mega.pk",
];

/** One click: a standing watcher and a parallel multi-agent comparison, side by side. */
export function launchDemo(sessionId: string) {
  launchGoal(sessionId, DEMO_GOALS[0]);
  setTimeout(() => launchGoal(sessionId, DEMO_GOALS[1]), 1500);
}

/** Scripted Toolsmith loop (or, with sneaky, a malicious build that must be blocked). */
export function launchToolsmithDemo(sessionId: string, sneaky = false) {
  post("/api/debug/toolsmith_demo", { run_id: newId(), session_id: sessionId, sneaky }).catch(console.error);
}

/** confirm=false from voice: the API refuses high-risk approvals without a real click. */
export async function decide(approvalId: string, decision: string, opts: { note?: string; confirm?: boolean } = {}) {
  const r = await post(`/api/approvals/${approvalId}/decide`, { decision, note: opts.note, confirm: opts.confirm ?? false });
  return { ok: r.ok, detail: r.ok ? "" : ((await r.json().catch(() => ({}))).detail ?? "Failed") as string };
}

export function controlAgent(agentId: string, action: string, text?: string) {
  return post(`/api/agents/${agentId}/control`, { action, text });
}

export function simulateEmail(preset: string) {
  return post("/api/demo/emails", { preset });
}
