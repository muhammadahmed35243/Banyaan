"use client";

import { useRouter } from "next/navigation";
import { newId } from "@/lib/ids";

/** Opens a fresh session. The id is made on click, so a prerendered page never shares one. */
export default function NewSessionButton({ className, children }: { className: string; children: React.ReactNode }) {
  const router = useRouter();
  return (
    <button type="button" className={className} onClick={() => router.push(`/session?id=${newId()}`)}>
      {children}
    </button>
  );
}
