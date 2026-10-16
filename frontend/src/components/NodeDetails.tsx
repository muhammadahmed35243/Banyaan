"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import { useBanyan } from "@/store/useBanyan";

export default function NodeDetails() {
  const node = useBanyan((s) => (s.selectedId ? s.nodes[s.selectedId] : null));
  const select = useBanyan((s) => s.select);
  const [text, setText] = useState("");
  if (!node) return null;

  const control = (action: string, withText = false) => {
    fetch(`${API_URL}/api/agents/${node.id}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, text: withText ? text : undefined }),
    }).catch(console.error);
    if (withText) setText("");
  };
  const btn = "rounded px-2 py-1 text-xs";

  return (
    <div className="border-t border-slate-800 bg-slate-950 px-5 py-3 text-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-400">
            {node.role} · {node.status.replace("_", " ")} · {node.tokensUsed} tokens
            {node.confidence !== null && ` · ${(node.confidence * 100).toFixed(0)}% confident`}
          </div>
          <div className="mt-1 font-medium">{node.goal}</div>
          {node.result && <p className="mt-1 max-w-3xl text-xs text-slate-300">{node.result}</p>}
        </div>
        <button onClick={() => select(null)} className="text-slate-500 hover:text-slate-300">✕</button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button onClick={() => control("pause")} className={`${btn} bg-slate-700 hover:bg-slate-600`}>Pause</button>
        <button onClick={() => control("resume")} className={`${btn} bg-slate-700 hover:bg-slate-600`}>Resume</button>
        <button onClick={() => control("prune")} className={`${btn} bg-red-700 hover:bg-red-600`}>Prune</button>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="New goal or a note…"
          className="min-w-64 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" />
        <button disabled={!text} onClick={() => control("redirect", true)}
          className={`${btn} bg-blue-700 hover:bg-blue-600 disabled:opacity-40`}>Redirect</button>
        <button disabled={!text} onClick={() => control("inject", true)}
          className={`${btn} bg-slate-700 hover:bg-slate-600 disabled:opacity-40`}>Add note</button>
      </div>
    </div>
  );
}
