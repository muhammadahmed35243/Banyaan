import { WS_URL } from "./config";
import { useBanyan, type BanyanEvent } from "@/store/useBanyan";

/** Connect to a run's event stream; reconnects automatically. Returns a disconnect fn. */
export function connectRun(runId: string): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    ws = new WebSocket(`${WS_URL}/ws/${runId}`);
    ws.onmessage = (m) => useBanyan.getState().applyEvent(JSON.parse(m.data) as BanyanEvent);
    // Server replays full history on connect; the store de-dupes by event id.
    ws.onclose = () => {
      if (!closed) retry = setTimeout(open, 1000);
    };
  };
  open();

  return () => {
    closed = true;
    clearTimeout(retry);
    ws?.close();
  };
}
