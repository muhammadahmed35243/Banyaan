import { API_URL } from "./config";
import type { BanyanEvent } from "@/store/useBanyan";

/**
 * Agent narration. ElevenLabs (via the backend, three agent voices) when configured,
 * otherwise the browser's free speechSynthesis with a different pitch per role.
 * Short lines only, and at most two queued, so it never talks over the demo.
 */
type Role = "orchestrator" | "builder" | "critic" | "watcher";
const BROWSER_STYLE: Record<Role, { pitch: number; rate: number }> = {
  orchestrator: { pitch: 1, rate: 1.05 },
  builder: { pitch: 1.25, rate: 1.1 },
  critic: { pitch: 0.6, rate: 0.95 },
  watcher: { pitch: 1.1, rate: 1.0 },
};

let enabled = false;
let provider: "browser" | "elevenlabs" = "browser";
let busy = false;
const queue: { text: string; role: Role }[] = [];
const listeners = new Set<(speaking: boolean) => void>();

export const onSpeaking = (fn: (s: boolean) => void) => {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
};
const setSpeaking = (s: boolean) => listeners.forEach((fn) => fn(s));
export const voiceEnabled = () => enabled;

/** Must run from a click: browsers only allow audio after a user gesture. */
export async function enableVoice() {
  if (enabled) return;
  enabled = true;
  try {
    provider = ((await (await fetch(`${API_URL}/api/voice/config`)).json()).provider) ?? "browser";
  } catch { provider = "browser"; }
}
export function disableVoice() {
  enabled = false;
  queue.length = 0;
  if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
}

export function say(text: string, role: string = "orchestrator") {
  if (!enabled || !text) return;
  if (queue.length >= 2) queue.shift(); // keep it current: drop the oldest pending line
  queue.push({ text: text.slice(0, 220), role: (role in BROWSER_STYLE ? role : "orchestrator") as Role });
  void pump();
}

async function pump() {
  if (busy || queue.length === 0) return;
  busy = true;
  setSpeaking(true);
  const { text, role } = queue.shift()!;
  try {
    if (provider === "elevenlabs") await playEleven(text, role);
    else await speakBrowser(text, role);
  } catch {
    await speakBrowser(text, role).catch(() => {});
  }
  busy = false;
  setSpeaking(false);
  void pump();
}

async function playEleven(text: string, role: Role) {
  const r = await fetch(`${API_URL}/api/voice/speak`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, role }),
  });
  if (!r.ok) throw new Error("tts");
  const url = URL.createObjectURL(await r.blob());
  await new Promise<void>((res) => {
    const a = new Audio(url);
    a.onended = a.onerror = () => { URL.revokeObjectURL(url); res(); };
    a.play().catch(() => res());
  });
}

function speakBrowser(text: string, role: Role) {
  return new Promise<void>((res) => {
    if (typeof speechSynthesis === "undefined") return res();
    const u = new SpeechSynthesisUtterance(text);
    Object.assign(u, BROWSER_STYLE[role]);
    const en = speechSynthesis.getVoices().find((v) => v.lang.startsWith("en") && /Google|Natural|Samantha|Daniel/.test(v.name));
    if (en) u.voice = en;
    u.onend = u.onerror = () => res();
    speechSynthesis.speak(u);
    setTimeout(res, 15000); // never get stuck if the engine drops onend
  });
}

const NEEDS_HUMAN_LINE: Record<string, string> = {
  new_tool: "A new tool needs your approval.",
  watch_setup: "A watcher needs access to your inbox.",
  connect_google: "Please sign in with Google so I can send this email.",
  risky_action: "This action needs your click before I continue.",
  low_confidence: "I'm not sure about one answer. Please check it.",
  budget: "A branch is over its budget.",
};

/** Turn important live events into short spoken lines. */
export function narrate(e: BanyanEvent) {
  const p = e.payload;
  if (e.type === "speak") say(String(p.text ?? ""), String(p.role ?? "orchestrator"));
  else if (e.type === "needs_human" && NEEDS_HUMAN_LINE[p.kind as string]) say(NEEDS_HUMAN_LINE[p.kind as string]);
  else if (e.type === "run_finished" && p.result) say("Task complete.");
}
