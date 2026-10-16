import { API_URL } from "./config";
import { useBanyan, type BanyanEvent } from "@/store/useBanyan";

const POLL_MS = 600;
const TICK_MS = 5000;

/**
 * Follow every run in a session by polling with one sequence cursor (Vercel functions
 * can't hold WebSockets). The first poll uses after=0, which replays the session on refresh.
 * While any watcher is alive, also "tick" the session: serverless can't run an agent in the
 * background, so the open page wakes the watchers (the server rate-limits each one).
 * Returns a disconnect fn.
 */
export function connectSession(sessionId: string): () => void {
  let cursor = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const poll = async () => {
    try {
      const r = await fetch(`${API_URL}/api/sessions/${sessionId}/events?after=${cursor}`);
      const data = (await r.json()) as { events: BanyanEvent[]; cursor: number };
      cursor = data.cursor;
      data.events.forEach((e) => useBanyan.getState().applyEvent(e));
    } catch (err) {
      console.error("poll failed", err);
    }
    if (!stopped) timer = setTimeout(poll, POLL_MS);
  };
  poll();

  const ticker = setInterval(() => {
    const live = Object.values(useBanyan.getState().nodes).some(
      (n) => n.role === "watcher" && ["watching", "running_tool", "thinking"].includes(n.status));
    if (live) fetch(`${API_URL}/api/sessions/${sessionId}/tick`, { method: "POST" }).catch(() => {});
  }, TICK_MS);

  return () => {
    stopped = true;
    clearTimeout(timer);
    clearInterval(ticker);
  };
}
