"use client";

import { Suspense, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ApprovalInbox from "@/components/ApprovalInbox";
import NodeDetails from "@/components/NodeDetails";
import AgentTree from "@/components/AgentTree";
import GoalInput from "@/components/GoalInput";
import { connectRun } from "@/lib/ws";
import { useBanyan } from "@/store/useBanyan";

function MissionControl() {
  const router = useRouter();
  const runId = useSearchParams().get("run");

  // The run id lives in the URL, so a refresh reconnects and the server replays the run.
  useEffect(() => {
    if (!runId) return;
    useBanyan.getState().reset();
    return connectRun(runId);
  }, [runId]);

  const onRun = useCallback((id: string) => router.push(`/?run=${id}`), [router]);

  return (
    <div className="flex h-screen flex-col">
      <GoalInput onRun={onRun} />
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
