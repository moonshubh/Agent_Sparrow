"use client";

import React from "react";
import dynamic from "next/dynamic";

// Sprint 0: Clean rebuild with minimal working chat interface
const CopilotSidebarClient = dynamic(
  () => import("./copilot/CopilotSidebarClient"),
  { ssr: false }
);

export default function AIChatPage() {
  return (
    <CopilotSidebarClient />
  );
}
