"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ApprovalInbox from "@/components/ApprovalInbox";
import NodeDetails from "@/components/NodeDetails";
import AgentTree from "@/components/AgentTree";
import GoalInput from "@/components/GoalInput";
import Conversation from "@/components/Conversation";
import SystemMap from "@/components/SystemMap";
import Swimlanes from "@/components/Swimlanes";
import { connectSession } from "@/lib/ws";
import { newId } from "@/lib/ids";
import { useBanyan } from "@/store/useBanyan";

function MissionControl() {
  const router = useRouter();
  const sessionId = useSearchParams().get("id");
  const view = useBanyan((s) => s.view);
  const setView = useBanyan((s) => s.setView);

  // The session id lives in the URL: every goal typed here joins it and runs side by side,
  // and a refresh replays the whole session from stored events.
  useEffect(() => {
    if (!sessionId) {
      router.replace(`/session?id=${newId()}`);
      return;
    }
    useBanyan.getState().reset();
    return connectSession(sessionId);
  }, [sessionId, router]);

  if (!sessionId) return null;
  return (
    <div className="flex h-screen flex-col">
      <GoalInput sessionId={sessionId} onNewSession={() => router.push(`/session?id=${newId()}`)} />
      <div className="flex min-h-0 flex-1">
        <Conversation sessionId={sessionId} />
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex gap-1 border-b border-slate-800 px-4 py-1.5 text-xs">
            {(["tree", "map", "timeline"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)}
                className={`rounded px-3 py-1 ${view === v ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
                {v === "tree" ? "🌳 Agent tree" : v === "map" ? "🛰️ System map" : "📊 Timeline"}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1">
            {view === "tree" ? <AgentTree /> : view === "map" ? <SystemMap /> : <Swimlanes />}
          </div>
          <NodeDetails />
        </main>
        <ApprovalInbox />
      </div>
    </div>
  );
}

export default function SessionPage() {
  return (
    <Suspense>
      <MissionControl />
    </Suspense>
  );
}
