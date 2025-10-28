"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LegacyRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/chat/copilot');
  }, [router]);
  return (
    <div className="min-h-svh w-full flex items-center justify-center p-8">
      <div className="text-center text-sm text-muted-foreground">Legacy chat retired. Redirecting…</div>
    </div>
  );
}

