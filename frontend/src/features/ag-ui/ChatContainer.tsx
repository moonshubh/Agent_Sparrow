'use client';

import React, { useEffect, useRef, useState, useMemo } from 'react';
import { useAgent } from './hooks/useAgent';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { ChatHeader } from './ChatHeader';
import type { AttachmentInput } from '@/services/ag-ui/types';
import type { AgentChoice } from '@/features/ag-ui/hooks/useAgentSelection';
import type { Provider, ProviderAvailability } from '@/services/api/endpoints/models';
import { TimelineOperation } from './timeline/AgenticTimelineView';
import { ThinkingTrace } from './sidebar/ThinkingTrace';
import { ToolEvidenceSidebar } from './evidence/ToolEvidenceSidebar';
import { EnhancedReasoningPanel, PhaseData, ReasoningPhase } from './reasoning/EnhancedReasoningPanel';
import { ArtifactProvider, ArtifactPanel } from './artifacts';

interface ChatContainerProps {
  sessionId: string;
  agentType?: AgentChoice;
  onAgentChange?: (agentType: AgentChoice) => void;
  provider?: Provider;
  onProviderChange?: (provider: Provider) => void;
  availableProviders?: ProviderAvailability;
  model?: string;
  onModelChange?: (model: string) => void;
  memoryEnabled?: boolean;
  onMemoryToggle?: (enabled: boolean) => void;
  models?: string[];
  modelHelperText?: string;
  recommendedModel?: string;
}

export function ChatContainer({
  sessionId,
  agentType = 'auto',
  onAgentChange,
  provider = 'google',
  onProviderChange,
  availableProviders = { google: true, xai: false },
  model = 'gemini-2.5-flash',
  onModelChange,
  memoryEnabled = true,
  onMemoryToggle,
  models = ['gemini-2.5-flash', 'gemini-2.5-pro'],
  modelHelperText,
  recommendedModel,
}: ChatContainerProps) {
  const {
    messages,
    isStreaming,
    sendMessage,
    abortRun,
    error,
    agent,
    activeTools,
    timelineOperations,
    currentOperationId,
    toolEvidence,
    todos,
    thinkingTrace,
    activeTraceStepId,
    setActiveTraceStep,
    isTraceCollapsed,
    setTraceCollapsed,
    resolvedTaskType,
    resolvedModel,
  } = useAgent();
  const containerRef = useRef<HTMLDivElement>(null);
  const [attachments, setAttachments] = useState<AttachmentInput[]>([]);
  const normalizedAgentType: AgentChoice = agentType === 'log_analysis'
    ? 'log_analysis'
    : agentType === 'research'
      ? 'research'
      : agentType === 'auto'
        ? 'primary'
        : agentType;
  const agentLabels: Record<AgentChoice, string> = {
    auto: 'Auto Route',
    primary: 'Primary Support',
    log_analysis: 'Log Analysis',
    research: 'Research'
  };
  const hasConversation = messages.some((message) =>
    message.role === 'user' || message.role === 'assistant'
  );

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
      provider,
      model,
      agent_type: agentType === 'auto' ? undefined : agentType,
      use_server_memory: memoryEnabled,
    });
  }, [agent, provider, model, agentType, memoryEnabled]);

  const handleSendMessage = async (content: string) => {
    await sendMessage(content, attachments);
    // Clear attachments after sending
    setAttachments([]);
  };

  // Map timeline operations to reasoning phases
  const phases = useMemo(() => {
    if (timelineOperations.length === 0) return [];

    const phases: PhaseData[] = [];

    // 1. Planning Phase
    const planningOp = timelineOperations.find(op => op.type === 'agent' && op.name === 'Unified Agent');
    phases.push({
      phase: 'planning',
      title: 'Strategic Planning',
      description: 'Analyzing request and formulating execution plan',
      status: planningOp ? (planningOp.status === 'running' && timelineOperations.length <= 1 ? 'active' : 'complete') : 'pending',
      duration: planningOp?.duration,
      thinkingSteps: [
        'Decomposing user request',
        'Identifying necessary tools',
        'Checking memory context'
      ]
    });

    // 2. Searching Phase
    const searchTools = timelineOperations.filter(op =>
      op.type === 'tool' &&
      (op.name.includes('search') || op.name.includes('retriev') || op.name.includes('memory'))
    );

    if (searchTools.length > 0) {
      const isRunning = searchTools.some(op => op.status === 'running');
      phases.push({
        phase: 'searching',
        title: 'Information Gathering',
        description: `Executing ${searchTools.length} search operations`,
        status: isRunning ? 'active' : 'complete',
        toolDecisions: searchTools.map(op => ({
          toolName: op.name,
          selected: true,
          reason: 'Required for context',
          confidence: 0.9
        }))
      });
    }

    // 3. Analyzing Phase
    const analysisTools = timelineOperations.filter(op =>
      op.type === 'tool' &&
      !op.name.includes('search') && !op.name.includes('retriev') && !op.name.includes('memory')
    );

    if (analysisTools.length > 0 || (searchTools.length > 0 && searchTools.every(op => op.status === 'success'))) {
      const isRunning = analysisTools.some(op => op.status === 'running');
      const isAnalyzing = isRunning || (searchTools.every(op => op.status === 'success') && planningOp?.status === 'running' && !isStreaming);

      phases.push({
        phase: 'analyzing',
        title: 'Deep Analysis',
        description: 'Processing gathered information and computing results',
        status: isAnalyzing ? 'active' : (analysisTools.every(op => op.status === 'success') ? 'complete' : 'pending'),
        toolDecisions: analysisTools.map(op => ({
          toolName: op.name,
          selected: true,
          reason: 'Data processing required',
          confidence: 0.95
        }))
      });
    }

    // 4. Responding Phase
    if (isStreaming && timelineOperations.every(op => op.type !== 'tool' || op.status !== 'running')) {
      phases.push({
        phase: 'responding',
        title: 'Response Generation',
        description: 'Synthesizing final answer for user',
        status: 'active'
      });
    } else if (planningOp?.status === 'success') {
      phases.push({
        phase: 'responding',
        title: 'Response Generation',
        description: 'Synthesizing final answer for user',
        status: 'complete'
      });
    }

    return phases;
  }, [timelineOperations, isStreaming]);

  const currentPhase = phases.find(p => p.status === 'active')?.phase || undefined;

  const isEmptyState = !hasConversation;
  const hasAgentActivity = !isEmptyState; // Always show sidebar when chatting
  const activeOperation = currentOperationId
    ? timelineOperations.find((op) => op.id === currentOperationId)
    : undefined;
  const pendingTodos = todos.filter((t) => (t.status || 'pending') === 'pending');
  const inProgressTodos = todos.filter((t) => (t.status || 'pending') === 'in_progress');
  const runStatus: 'idle' | 'running' | 'error' = error
    ? 'error'
    : (isStreaming || activeOperation?.status === 'running')
      ? 'running'
      : 'idle';
  const statusMessage = error?.message
    ? error.message
    : isStreaming
      ? agentType === 'log_analysis'
        ? 'Deep log analysis in progress (Pro model takes longer for thorough results)'
        : `Working on ${activeOperation?.name || 'response'}`
      : hasConversation
        ? 'Ready for the next instruction'
        : 'Waiting for your first question';
  const focusLabel = activeOperation?.name || (currentPhase ? `${currentPhase} phase` : 'Idle');
  const agentDisplayName = agentLabels[agentType] || 'Primary Support';

  return (
    <ArtifactProvider>
    <main className="h-screen w-screen flex flex-col bg-background text-foreground font-serif overflow-hidden">
      <ChatHeader
        agentType={agentType}
        onAgentChange={(newType) => onAgentChange?.(newType)}
        provider={provider}
        onProviderChange={(p) => onProviderChange?.(p)}
        availableProviders={availableProviders}
        model={resolvedModel || model}
        onModelChange={(newModel) => onModelChange?.(newModel)}
        memoryEnabled={memoryEnabled}
        onMemoryToggle={(enabled) => onMemoryToggle?.(enabled)}
        models={models}
        modelHelperText={modelHelperText}
        recommendedModel={recommendedModel}
        activeTools={activeTools}
        hasActiveConversation={hasConversation}
        resolvedTaskType={resolvedTaskType}
      />

      <div className="flex-1 flex overflow-hidden relative">
        {/* Main Chat Area - Left/Center */}
        <div
          ref={containerRef}
          className="flex-1 flex flex-col min-w-0 overflow-y-auto scroll-smooth"
        >
          <div className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-6 flex flex-col">
            {isEmptyState ? (
              <div className="flex-1 flex flex-col items-center justify-center pb-32 animate-in fade-in duration-700">
                {/* Centered Input for Empty State */}
                <ChatInput
                  onSend={handleSendMessage}
                  onAbort={abortRun}
                  disabled={isStreaming}
                  attachments={attachments}
                  onAttachmentsChange={setAttachments}
                  sessionId={sessionId}
                  agentType={normalizedAgentType}
                  variant="centered"
                />
              </div>
            ) : (
              <>
                <MessageList messages={messages} isStreaming={isStreaming} agentType={agentType} />

                {error && (
                  <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                    <p className="text-red-400 font-medium">Error</p>
                    <p className="text-red-300 text-sm mt-1">{error.message}</p>
                  </div>
                )}

                {/* Spacer for bottom input */}
                <div className="h-24" />
              </>
            )}
          </div>

          {/* Input Area - Fixed at bottom (Only when not empty) */}
          {!isEmptyState && (
            <div className="sticky bottom-0 p-6 bg-gradient-to-t from-background via-background to-transparent z-10 animate-in slide-in-from-bottom-10 duration-500">
              <div className="max-w-4xl mx-auto">
                <ChatInput
                  onSend={handleSendMessage}
                  onAbort={abortRun}
                  disabled={isStreaming}
                  attachments={attachments}
                  onAttachmentsChange={setAttachments}
                  sessionId={sessionId}
                  agentType={normalizedAgentType}
                  variant="default"
                />
              </div>
            </div>
          )}
        </div>

        {/* Agent Sidebar - Right - Scholarly Panel */}
        {hasAgentActivity && (
          <div className="w-[400px] xl:w-[450px] border-l border-border bg-sidebar flex flex-col overflow-hidden transition-all duration-300 ease-in-out paper-texture">
            <div className="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar relative z-10">
              {/* Reasoning Panel */}
              <div className="animate-in fade-in slide-in-from-right-4 duration-500">
                <EnhancedReasoningPanel
                  phases={phases}
                  currentPhase={currentPhase}
                  isExpanded={true}
                  agentLabel={agentDisplayName}
                  runStatus={runStatus}
                  statusMessage={statusMessage}
                  activeOperationName={focusLabel}
                  activeToolCount={activeTools.length}
                  errorMessage={error?.message}
                  todoCount={todos.length}
                  inProgressTodoCount={inProgressTodos.length}
                  pendingTodoCount={pendingTodos.length}
                  todos={todos as any}
                />
              </div>

              {/* Timeline View */}
              <div className="animate-in fade-in slide-in-from-right-4 duration-500 delay-100">
                <ThinkingTrace
                  steps={thinkingTrace}
                  activeStepId={activeTraceStepId}
                  collapsed={isTraceCollapsed}
                  onCollapseToggle={() => setTraceCollapsed(!isTraceCollapsed)}
                  onStepFocus={setActiveTraceStep}
                  className="min-h-[320px]"
                  agentType={normalizedAgentType}
                />
              </div>

              {/* Evidence Sidebar - Research Notes */}
              <div className="animate-in fade-in slide-in-from-right-4 duration-500 delay-200">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 px-1">
                  Tool Evidence
                </h3>
                <ToolEvidenceSidebar
                  operations={timelineOperations}
                  toolEvidence={toolEvidence}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Artifact Panel - Modal overlay for viewing artifacts */}
      <ArtifactPanel />
    </main>
    </ArtifactProvider>
  );
}
