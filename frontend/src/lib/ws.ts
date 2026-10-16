import { API_URL } from "./config";
import { useBanyan, type BanyanEvent } from "@/store/useBanyan";

const POLL_MS = 600;

/** OS notification for a live alert (only if the user allowed it), useful when the tab is in the background. */
function desktopNotify(e: BanyanEvent) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  const p = e.payload;
  new Notification(`🔔 ${String(p.subject ?? "Banyan alert")}`, {
    body: `${String(p.summary ?? "")}${p.amount ? ` (${String(p.amount)})` : ""}`, tag: e.id,
  });
}
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
      const { live, applyEvent, setLive } = useBanyan.getState();
      data.events.forEach((e) => {
        applyEvent(e);
        if (live && e.type === "alert") desktopNotify(e);
      });
      if (!live) setLive(); // the first batch was history; from now on events are live
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
