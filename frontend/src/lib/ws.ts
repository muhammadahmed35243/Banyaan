import { API_URL } from "./config";
import { useBanyan, type BanyanEvent } from "@/store/useBanyan";

const POLL_MS = 600;

/**
 * Follow a run's events by polling with a sequence cursor (Vercel functions can't hold
 * WebSockets). The first poll uses after=0, which replays the whole run on refresh.
 * Returns a disconnect fn.
 */
export function connectRun(runId: string): () => void {
  let cursor = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const poll = async () => {
    try {
      const r = await fetch(`${API_URL}/api/runs/${runId}/events?after=${cursor}`);
      const data = (await r.json()) as { events: BanyanEvent[]; cursor: number };
      cursor = data.cursor;
      data.events.forEach((e) => useBanyan.getState().applyEvent(e));
    } catch (err) {
      console.error("poll failed", err);
    }
    if (!stopped) timer = setTimeout(poll, POLL_MS);
  };
  poll();

  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}
