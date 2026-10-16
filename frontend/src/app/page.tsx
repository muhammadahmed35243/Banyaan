"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ApprovalInbox from "@/components/ApprovalInbox";
import NodeDetails from "@/components/NodeDetails";
import AgentTree from "@/components/AgentTree";
import GoalInput from "@/components/GoalInput";
import { connectSession } from "@/lib/ws";
import { newId } from "@/lib/ids";
import { useBanyan } from "@/store/useBanyan";

function MissionControl() {
  const router = useRouter();
  const sessionId = useSearchParams().get("session");

  // The session id lives in the URL: every goal typed here joins it and runs side by side,
  // and a refresh replays the whole session from stored events.
  useEffect(() => {
    if (!sessionId) {
      router.replace(`/?session=${newId()}`);
      return;
    }
    useBanyan.getState().reset();
    return connectSession(sessionId);
  }, [sessionId, router]);

  if (!sessionId) return null;
  return (
    <div className="flex h-screen flex-col">
      <GoalInput sessionId={sessionId} onNewSession={() => router.push(`/?session=${newId()}`)} />
      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1"><AgentTree /></div>
          <NodeDetails />
        </main>
        <ApprovalInbox />
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <MissionControl />
    </Suspense>
  );
}
