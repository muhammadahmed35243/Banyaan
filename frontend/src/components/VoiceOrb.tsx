"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/config";
import { controlAgent, decide, launchGoal, simulateEmail } from "@/lib/actions";
import { disableVoice, enableVoice, onSpeaking, say, voiceEnabled } from "@/lib/voice";
import { useBanyan } from "@/store/useBanyan";

/* Chrome ships the Web Speech API prefixed and without TS types. */
interface Recognition {
  lang: string; interimResults: boolean; maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> & { length: number } }) => void) | null;
  onerror: (() => void) | null; onend: (() => void) | null;
  start: () => void; stop: () => void;
}
const getRecognition = (): (new () => Recognition) | null => {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

/** Execute a parsed voice intent with the same calls the buttons use. */
async function execute(intent: { intent: string; target: string | null; text: string | null }, sessionId: string) {
  const s = useBanyan.getState();
  const pending = Object.values(s.approvals).filter((a) => a.status === "pending");
  const active = Object.values(s.nodes).filter((n) => ["thinking", "running_tool", "watching", "paused", "waiting_human"].includes(n.status));
  const target = (s.selectedId && s.nodes[s.selectedId]) || active[active.length - 1];

  switch (intent.intent) {
    case "new_goal":
      if (!intent.text) return say("Sorry, I didn't catch that.");
      launchGoal(sessionId, intent.text);
      return say("On it.");
    case "approve": {
      const a = pending[0];
      if (!a) return say("Nothing is waiting for approval.");
      const r = await decide(a.id, "approved"); // no confirm: high risk still needs a click
      return say(r.ok ? "Approved." : a.risk === "high" ? "That one is high risk. Please click approve yourself." : r.detail);
    }
    case "reject": {
      const a = pending[0];
      if (!a) return say("Nothing is waiting for a decision.");
      const r = await decide(a.id, "rejected", { note: intent.text ?? "Rejected by voice" });
      return say(r.ok ? "Rejected." : r.detail);
    }
    case "pause": case "resume": case "prune":
      if (!target) return say("There is no active agent.");
      await controlAgent(target.id, intent.intent);
      return say(`${intent.intent === "prune" ? "Stopped" : intent.intent === "pause" ? "Paused" : "Resumed"} the ${target.role}.`);
    case "status": {
      const working = active.filter((n) => n.status !== "watching").length;
      const watching = active.filter((n) => n.status === "watching").length;
      return say(`${working} agents working${watching ? `, ${watching} watching` : ""}, ${pending.length} waiting for you.`);
    }
    case "explain": {
      const n = (s.selectedId && s.nodes[s.selectedId]) || Object.values(s.nodes).filter((x) => x.result && x.depth === 0).pop();
      return say(n?.result ? n.result.slice(0, 200) : "Nothing has finished yet.");
    }
    case "show_code":
      s.setView("tree");
      return say(pending.some((a) => a.kind === "new_tool") ? "The code is open in the approval card." : "No new tool is waiting.");
    case "view":
      s.setView((intent.target as "tree" | "map" | "timeline") ?? "tree");
      return say(`Showing the ${intent.target === "map" ? "system map" : intent.target ?? "tree"}.`);
    case "demo_email":
      await simulateEmail("payment");
      return say("Sending a test bill to the demo inbox.");
  }
}

export default function VoiceOrb({ sessionId }: { sessionId: string }) {
  const [on, setOn] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeakingState] = useState(false);
  const [lang, setLang] = useState<"en-US" | "ur-PK">("en-US");
  const [heard, setHeard] = useState("");
  const rec = useRef<Recognition | null>(null);

  useEffect(() => onSpeaking(setSpeakingState), []);

  const listen = async () => {
    if (!voiceEnabled()) { await enableVoice(); setOn(true); }
    const SR = getRecognition();
    if (!SR) { say("Voice commands need Chrome."); setHeard("Voice input needs Chrome"); return; }
    if (listening) { rec.current?.stop(); return; }
    const r = new SR();
    r.lang = lang;
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.onresult = async (e) => {
      const text = e.results[0][0].transcript;
      setHeard(`“${text}”`);
      try {
        const intent = await (await fetch(`${API_URL}/api/voice/command`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ transcript: text }),
        })).json();
        await execute(intent, sessionId);
      } catch { say("I couldn't reach the server."); }
      setTimeout(() => setHeard(""), 6000);
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };

  const ring = listening ? "bg-red-500 shadow-[0_0_20px_4px_rgba(239,68,68,0.6)] animate-pulse"
    : speaking ? "bg-cyan-400 shadow-[0_0_24px_6px_rgba(34,211,238,0.6)] animate-pulse"
      : on ? "bg-emerald-500/80 shadow-[0_0_12px_2px_rgba(16,185,129,0.4)]" : "bg-slate-700";

  return (
    <div className="relative flex items-center gap-1">
      <button onClick={listen} title={on ? "Click and speak a command or a goal" : "Turn on voice (Banyan speaks + listens)"}
        className={`grid h-8 w-8 place-items-center rounded-full text-sm transition-all ${ring}`}>
        {listening ? "●" : "🎙"}
      </button>
      {on && (
        <>
          <button onClick={() => setLang((l) => (l === "en-US" ? "ur-PK" : "en-US"))} title="Language for voice input"
            className="rounded px-1 text-[10px] text-slate-400 hover:text-slate-200">{lang === "en-US" ? "EN" : "اردو"}</button>
          <button onClick={() => { disableVoice(); setOn(false); }} title="Mute Banyan"
            className="rounded px-1 text-[10px] text-slate-500 hover:text-slate-200">🔇</button>
        </>
      )}
      {heard && (
        <div className="absolute left-0 top-10 z-30 w-72 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 shadow-xl">
          {heard}
        </div>
      )}
    </div>
  );
}
