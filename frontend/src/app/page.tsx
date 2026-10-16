"use client";

import { Suspense, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
      <main className="flex-1">
        <AgentTree />
      </main>
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
