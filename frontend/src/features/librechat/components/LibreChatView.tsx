"use client";

import React, {
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
} from "react";
import type { Message } from "@/services/ag-ui/client";
import { useAgent } from "@/features/librechat/AgentContext";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { Landing } from "./Landing";
import { ArtifactPanel } from "@/features/librechat/artifacts";

interface LibreChatViewProps {
  sessionId?: string;
  onNewChat?: () => void;
  conversations?: Array<{ id: string; title: string; timestamp?: Date }>;
  onSelectConversation?: (id: string) => void;
  onRenameConversation?: (id: string, newTitle: string) => void;
  onDeleteConversation?: (id: string) => void;
  currentConversationId?: string;
  onAutoName?: (title: string) => void;
}

export function LibreChatView({
  sessionId,
  onNewChat,
  conversations = [],
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  currentConversationId,
  onAutoName,
}: LibreChatViewProps) {
  const { messages, isStreaming, error } = useAgent();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [initialInput, setInitialInput] = useState("");
  const hasAutoNamedRef = useRef(false);

  // Auto-name chat based on first user message
  useEffect(() => {
    if (hasAutoNamedRef.current) return;
    if (!onAutoName) return;

    // Find first user message
    const firstUserMessage = messages.find((msg) => msg.role === "user");
    if (!firstUserMessage) return;

    const content =
      typeof firstUserMessage.content === "string"
        ? firstUserMessage.content
        : "";
    if (!content.trim()) return;

    // Generate title from first ~50 chars, truncating at word boundary
    let title = content.slice(0, 50).trim();
    if (content.length > 50) {
      const lastSpace = title.lastIndexOf(" ");
      if (lastSpace > 20) {
        title = title.slice(0, lastSpace);
      }
      title += "...";
    }

    hasAutoNamedRef.current = true;
    onAutoName(title);
  }, [messages, onAutoName]);

  // Reset auto-name flag when conversation changes
  useEffect(() => {
    hasAutoNamedRef.current = false;
  }, [currentConversationId]);

  // Note: Artifact reset/restore is handled by LibreChatClient.tsx
  // when switching conversations via restoreArtifactsFromMessages()
  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const handleNewChat = useCallback(() => {
    onNewChat?.();
  }, [onNewChat]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      onSelectConversation?.(id);
    },
    [onSelectConversation],
  );

  const handleStarterClick = useCallback((prompt: string) => {
    setInitialInput(prompt);
  }, []);

  const handleInputUsed = useCallback(() => {
    // Clear initial input after it's been used
    setInitialInput("");
  }, []);

  // Filter to only show user and assistant messages (hide tool messages)
  const displayMessages = useMemo(() => {
    const filtered = messages.filter((msg) => {
      if (msg.role === "user") return true;
      if (msg.role !== "assistant") return false;
      const text = typeof msg.content === "string" ? msg.content.trim() : "";
      const metadata = msg.metadata as Record<string, unknown> | undefined;
      const artifacts = Array.isArray(metadata?.artifacts)
        ? metadata?.artifacts
        : undefined;
      const hasArtifacts = Boolean(artifacts && artifacts.length > 0);
      return Boolean(text) || hasArtifacts;
    });

    if (
      isStreaming &&
      filtered.length > 0 &&
      filtered[filtered.length - 1].role === "user"
    ) {
      // Streaming placeholder message while waiting for assistant response
      const placeholderMessage: Message = {
        id: "streaming-placeholder",
        role: "assistant",
        content: "",
      };
      filtered.push(placeholderMessage);
    }

    return filtered;
  }, [messages, isStreaming]);

  const isLandingPage = messages.length === 0 && !isStreaming;

  return (
    <div className="lc-layout">
      {/* Left Sidebar - Conversation History */}
      <Sidebar
        isOpen={sidebarOpen}
        isCollapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        onNewChat={handleNewChat}
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onRenameConversation={onRenameConversation}
        onDeleteConversation={onDeleteConversation}
      />

      {/* Main Chat Area */}
      <main className="lc-main" role="main" aria-label="Chat area">
        {/* Header */}
        <Header onToggleSidebar={toggleSidebar} sidebarOpen={sidebarOpen} />

        {/* Content */}
        {isLandingPage ? (
          <Landing onStarterClick={handleStarterClick} />
        ) : (
          <MessageList
            messages={displayMessages}
            isStreaming={isStreaming}
            sessionId={sessionId}
          />
        )}

        {/* Error Display */}
        {error && (
          <div className="lc-error-banner" role="alert">
            <span>Error: {error.message}</span>
          </div>
        )}

        {/* Input Area - keep mounted to avoid layout flicker */}
        <ChatInput
          isLanding={isLandingPage}
          initialInput={initialInput}
          onInitialInputUsed={handleInputUsed}
        />
      </main>

      <ArtifactPanel />
    </div>
  );
}

export default LibreChatView;
