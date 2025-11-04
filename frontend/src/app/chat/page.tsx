"use client";

import React from "react";
import dynamic from "next/dynamic";

// Phase 3: Dynamic import for CopilotSidebarClient
const CopilotSidebarClient = dynamic(
  () => import("./copilot/CopilotSidebarClient"),
  { ssr: false }
);

export default function AIChatPage() {
  return (
    <CopilotSidebarClient />
  );
}
