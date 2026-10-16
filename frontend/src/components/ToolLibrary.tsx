"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/config";
import { useBanyan } from "@/store/useBanyan";

interface Tool {
  name: string; description: string; risk_level: string; status: string;
  usage_count?: number; version?: number; approved_at?: string | null; allowed_domains?: string[];
}
interface Library { builtin: Tool[]; grown: Tool[]; started_with: number; human_approved: number }

export default function ToolLibrary() {
  const [open, setOpen] = useState(false);
  const [lib, setLib] = useState<Library | null>(null);
  // Refresh when a tool gets hot-loaded (tool_loaded event) or the drawer opens.
  const loaded = useBanyan((s) => s.toolsLoaded);

  const load = useCallback(() => {
    fetch(`${API_URL}/api/tools`).then((r) => r.json()).then(setLib).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load, loaded, open]);

  const disable = async (name: string) => {
    await fetch(`${API_URL}/api/tools/${name}/disable`, { method: "POST" });
    load();
  };

  return (
    <>
      <button onClick={() => setOpen((o) => !o)}
        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800">
        🧰 {lib ? `Started with ${lib.started_with} tools · Humans approved ${lib.human_approved}` : "Tools"}
      </button>
      {open && lib && (
        <div className="absolute right-4 top-14 z-20 max-h-[70vh] w-96 overflow-auto rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-2xl">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Built-in</h3>
          {lib.builtin.map((t) => (
            <div key={t.name} className="mb-1 flex justify-between text-xs">
              <span className="font-mono">{t.name}</span><span className="text-slate-500">{t.description}</span>
            </div>
          ))}
          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-purple-300">Grown (human-approved)</h3>
          {lib.grown.length === 0 && <p className="text-xs text-slate-500">None yet. Ask for something Banyan cannot do.</p>}
          {lib.grown.map((t) => (
            <div key={t.name} className="mb-2 rounded border border-purple-900 bg-slate-900 p-2 text-xs">
              <div className="flex justify-between">
                <span className="font-mono">{t.name} v{t.version}</span>
                <span className={t.status === "active" ? "text-emerald-400" : "text-slate-500"}>{t.status}</span>
              </div>
              <div className="text-slate-400">{t.description}</div>
              <div className="mt-1 text-slate-500">
                used {t.usage_count}× · {t.risk_level} risk · {(t.allowed_domains ?? []).join(", ")}
              </div>
              {t.status === "active" && (
                <button onClick={() => disable(t.name)} className="mt-1 rounded bg-slate-700 px-2 py-0.5 hover:bg-slate-600">Disable</button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
