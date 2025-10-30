"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import CopilotChatClient from "./copilot/CopilotChatClient";
import { SidebarProvider, SidebarInset } from "@/shared/ui/sidebar";
import AppSidebarLeft, { type LeftTab } from "@/app/chat/components/AppSidebarLeft";
import RightContextSidebar from "@/app/chat/components/RightContextSidebar";
import { sessionsAPI } from "@/services/api/endpoints/sessions";

// Phase 3: Dynamic import for CopilotSidebarClient
const CopilotSidebarClient = dynamic(
  () => import("./copilot/CopilotSidebarClient"),
  { ssr: false }
);

/**
 * Phase 3: Feature Flag Toggle
 *
 * NEXT_PUBLIC_USE_COPILOT_UI_COMPONENTS controls which UI to render:
 * - false (default): Custom chat UI with manual rendering (CopilotChatClient)
 * - true: CopilotKit polished UI with CopilotSidebar
 *
 * Rollback: Set flag to false and restart frontend
 */
export default function AIChatPage() {
  const [activeTab, setActiveTab] = useState<LeftTab>('primary');
  const [sessionId, setSessionId] = useState<string>('');
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  const [rightPanelTop, setRightPanelTop] = useState<number>(96);
  const [rightPanelLeft, setRightPanelLeft] = useState<number | undefined>(undefined);
  const rightAutoCloseTimerRef = useRef<number | null>(null);

  // Phase 3: Check feature flag
  const useCopilotUI =
    process.env.NEXT_PUBLIC_USE_COPILOT_UI_COMPONENTS === "true";

  const openRightSidebar = useCallback((top?: number, left?: number) => {
    if (typeof top === 'number' && !Number.isNaN(top)) {
      setRightPanelTop(Math.max(64, Math.round(top)));
    }
    if (typeof left === 'number' && !Number.isNaN(left)) {
      setRightPanelLeft(Math.max(0, Math.round(left)));
    }
    setIsRightSidebarOpen(true);
    if (rightAutoCloseTimerRef.current) {
      window.clearTimeout(rightAutoCloseTimerRef.current);
    }
    rightAutoCloseTimerRef.current = window.setTimeout(() => {
      setIsRightSidebarOpen(false);
      rightAutoCloseTimerRef.current = null;
    }, 3000);
  }, []);

  useEffect(() => {
    if (!isRightSidebarOpen) return;
    const cancelTimer = () => {
      if (rightAutoCloseTimerRef.current) {
        window.clearTimeout(rightAutoCloseTimerRef.current);
        rightAutoCloseTimerRef.current = null;
      }
    };
    const onDocMouseDown = (e: MouseEvent) => {
      const panel = document.getElementById('right-context-sidebar');
      if (panel && !panel.contains(e.target as Node)) {
        setIsRightSidebarOpen(false);
        cancelTimer();
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    const panel = document.getElementById('right-context-sidebar');
    if (panel) {
      panel.addEventListener('mouseenter', cancelTimer);
      panel.addEventListener('focusin', cancelTimer);
      panel.addEventListener('mousedown', cancelTimer);
    }
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      if (panel) {
        panel.removeEventListener('mouseenter', cancelTimer);
        panel.removeEventListener('focusin', cancelTimer);
        panel.removeEventListener('mousedown', cancelTimer);
      }
    };
  }, [isRightSidebarOpen]);

  const handleSelectSession = (id?: string) => {
    setSessionId(id || '');
  };

  const handleNewChat = useCallback(async () => {
    try {
      const desiredAgent: 'primary' | 'log_analysis' = activeTab === 'log' ? 'log_analysis' : 'primary';
      const session = await sessionsAPI.create(desiredAgent);
      const createdId = String(session.id);
      setSessionId(createdId);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('chat-session-updated', {
            detail: { sessionId: createdId, agentType: desiredAgent },
          }),
        );
        window.dispatchEvent(new Event('chat-sessions:refresh'));
      }
    } catch (e) {}
  }, [activeTab]);

  const activeSessionId = sessionId || undefined;
  const agentType = activeTab === 'log' ? 'log_analysis' : 'primary';

  // Phase 3: Conditional rendering based on feature flag
  if (useCopilotUI) {
    return (
      <CopilotSidebarClient
        initialSessionId={activeSessionId}
        agentType={agentType}
      />
    );
  }

  // Legacy custom UI (default)
  return (
    <SidebarProvider defaultOpen={true}>
      <AppSidebarLeft
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        onOpenRightSidebar={openRightSidebar}
        onNewChat={handleNewChat}
      />
      <RightContextSidebar
        activeTab={activeTab}
        sessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        isOpen={isRightSidebarOpen}
        top={rightPanelTop}
        left={rightPanelLeft}
      />
      <SidebarInset>
        <CopilotChatClient
          initialSessionId={activeSessionId}
          agentType={agentType}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}
