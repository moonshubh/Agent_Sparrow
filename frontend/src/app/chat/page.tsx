"use client";

import React from "react";
import dynamic from "next/dynamic";

// AG-UI Native client implementation
const AgUiChatClient = dynamic(
  () => import("@/features/ag-ui/AgUiChatClient"),
  { ssr: false }
);

export default function AIChatPage() {
  return (
    <AgUiChatClient />
  );
}
