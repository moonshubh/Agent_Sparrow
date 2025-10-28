"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import CopilotChatClient from "./copilot/CopilotChatClient";
import { SidebarProvider, SidebarInset } from "@/shared/ui/sidebar";
import AppSidebarLeft, { type LeftTab } from "@/app/chat/components/AppSidebarLeft";
import RightContextSidebar from "@/app/chat/components/RightContextSidebar";
import { sessionsAPI } from "@/services/api/endpoints/sessions";

export default function AIChatPage() {
  const [activeTab, setActiveTab] = useState<LeftTab>('primary');
  const [sessionId, setSessionId] = useState<string>('');
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  const [rightPanelTop, setRightPanelTop] = useState<number>(96);
  const [rightPanelLeft, setRightPanelLeft] = useState<number | undefined>(undefined);
  const rightAutoCloseTimerRef = useRef<number | null>(null);

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
          agentType={activeTab === 'log' ? 'log_analysis' : 'primary'}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}
