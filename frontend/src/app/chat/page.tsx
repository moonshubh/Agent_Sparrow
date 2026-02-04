"use client";

import React from "react";
import dynamic from "next/dynamic";

// LibreChat-style UI with ChatGPT aesthetic
const LibreChatClient = dynamic(
  () => import("@/features/librechat/LibreChatClient"),
  { ssr: false },
);

export default function AIChatPage() {
  return <LibreChatClient />;
}
