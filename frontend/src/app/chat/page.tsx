"use client";

import React from "react";
import dynamic from "next/dynamic";

// AG-UI Native client implementation
const AgUiChatClient = dynamic(
  () => import("./copilot/AgUiChatClient"),
  { ssr: false }
);

export default function AIChatPage() {
  return (
    <AgUiChatClient />
  );
}
