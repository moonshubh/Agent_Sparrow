'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useAgent } from './hooks/useAgent';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { ChatHeader } from '@/app/chat/copilot/ChatHeader';
import type { AttachmentInput } from '@/services/ag-ui/types';

interface ChatContainerProps {
  sessionId: string;
  agentType?: string;
  onAgentChange?: (agentType: string) => void;
  model?: string;
  onModelChange?: (model: string) => void;
  memoryEnabled?: boolean;
  onMemoryToggle?: (enabled: boolean) => void;
  models?: string[];
}

export function ChatContainer({
  sessionId,
  agentType = 'auto',
  onAgentChange,
  model = 'gemini-2.5-flash',
  onModelChange,
  memoryEnabled = true,
  onMemoryToggle,
  models = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro'],
}: ChatContainerProps) {
  const { messages, isStreaming, sendMessage, abortRun, error, agent } = useAgent();
  const containerRef = useRef<HTMLDivElement>(null);
  const [attachments, setAttachments] = useState<AttachmentInput[]>([]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (containerRef.current) {
      const { scrollHeight, clientHeight, scrollTop } = containerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

      // Only auto-scroll if user is near the bottom
      if (isNearBottom) {
        containerRef.current.scrollTop = scrollHeight;
      }
    }
  }, [messages]);

  // Update agent state when settings change
  useEffect(() => {
    if (!agent) return;

    // Use setState to update immutably
    agent.setState({
      ...agent.state,
      provider: 'google',
      model,
      agent_type: agentType === 'auto' ? undefined : agentType,
      use_server_memory: memoryEnabled,
    });
  }, [agent, model, agentType, memoryEnabled]);

  const handleSendMessage = async (content: string) => {
    await sendMessage(content, attachments);
    // Clear attachments after sending
    setAttachments([]);
  };

  return (
    <main className="h-screen w-screen flex flex-col bg-gray-50">
      <ChatHeader
        agentType={agentType}
        onAgentChange={(newType) => onAgentChange?.(newType)}
        model={model}
        onModelChange={(newModel) => onModelChange?.(newModel)}
        memoryEnabled={memoryEnabled}
        onMemoryToggle={(enabled) => onMemoryToggle?.(enabled)}
        models={models}
      />

      <div
        ref={containerRef}
        className="flex-1 overflow-auto p-6 space-y-4"
      >
        <MessageList messages={messages} isStreaming={isStreaming} />

        {error && (
          <div className="max-w-3xl mx-auto p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-600 font-medium">Error</p>
            <p className="text-red-500 text-sm mt-1">{error.message}</p>
          </div>
        )}
      </div>

      <ChatInput
        onSend={handleSendMessage}
        onAbort={abortRun}
        disabled={isStreaming}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        sessionId={sessionId}
      />
    </main>
  );
}