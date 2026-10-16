"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/config";
import { useBanyan } from "@/store/useBanyan";

interface Tool {
  name: string; description: string; risk_level: string; status: string;
  usage_count?: number; version?: number; approved_by?: string | null; approved_at?: string | null;
  allowed_domains?: string[]; composed_from?: string[]; tests_passed?: number | null; tests_total?: number | null;
  secret?: string;
}
interface Library { builtin: Tool[]; grown: Tool[]; connectors: Tool[]; started_with: number; human_approved: number }

/** Where a grown tool came from: the Toolsmith pipeline it passed and the human who approved it. */
function Lineage({ t }: { t: Tool }) {
  const chip = "rounded bg-slate-800 px-1.5 py-0.5";
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[10px] text-slate-300">
      <span className={chip}>🔧 Builder</span>→
      <span className={chip}>🧪 Tests {t.tests_passed ?? "?"}/{t.tests_total ?? "?"}</span>→
      <span className={chip}>🛡️ Critic</span>→
      <span className={`${chip} bg-emerald-900/60 text-emerald-200`}>
        👤 {t.approved_by ?? "human"}{t.approved_at && ` · ${new Date(t.approved_at).toLocaleDateString()}`}
      </span>
      {(t.composed_from ?? []).length > 0 && (
        <span className="ml-1 text-slate-500">uses {(t.composed_from ?? []).join(", ")}</span>
      )}
    </div>
  );
}

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
  const h3 = "mb-2 mt-4 text-xs font-semibold uppercase tracking-wide";

  return (
    <>
      <button onClick={() => setOpen((o) => !o)}
        className="whitespace-nowrap rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800">
        🧰 {lib ? `Started with ${lib.started_with} tools · Humans approved ${lib.human_approved}` : "Tools"}
      </button>
      {open && lib && (
        <div className="absolute right-4 top-14 z-20 max-h-[75vh] w-[28rem] overflow-auto rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-2xl">
          <h3 className={`${h3} mt-0 text-slate-400`}>Started with ({lib.builtin.length})</h3>
          {lib.builtin.map((t) => (
            <div key={t.name} className="mb-1 flex justify-between gap-3 text-xs">
              <span className="font-mono">{t.name}</span><span className="text-right text-slate-500">{t.description}</span>
            </div>
          ))}
          <h3 className={`${h3} text-cyan-300`}>Connectors (use a vault secret)</h3>
          {(lib.connectors ?? []).map((t) => (
            <div key={t.name} className="mb-1 flex justify-between gap-3 text-xs">
              <span className="font-mono">{t.name} <span className="text-yellow-400">🔐 {t.secret}</span></span>
              <span className="text-right text-slate-500">{t.description}</span>
            </div>
          ))}
          <h3 className={`${h3} text-purple-300`}>Grown by agents, approved by humans ({lib.grown.length})</h3>
          {lib.grown.length === 0 && <p className="text-xs text-slate-500">None yet. Try 📋 Script → 🔧 Toolsmith demo.</p>}
          {lib.grown.map((t) => (
            <div key={t.name} className="mb-2 rounded border border-purple-900 bg-slate-900 p-2 text-xs">
              <div className="flex justify-between">
                <span className="font-mono">{t.name} v{t.version}</span>
                <span className={t.status === "active" ? "text-emerald-400" : "text-slate-500"}>{t.status}</span>
              </div>
              <div className="text-slate-400">{t.description}</div>
              <div className="mt-1 text-slate-500">
                used {t.usage_count}× · {t.risk_level} risk · {(t.allowed_domains ?? []).join(", ") || "no network"}
              </div>
              <Lineage t={t} />
              {t.status === "active" && (
                <button onClick={() => disable(t.name)} className="mt-1.5 rounded bg-slate-700 px-2 py-0.5 hover:bg-slate-600">Disable</button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
