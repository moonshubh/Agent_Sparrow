/**
 * Advanced Agent Integration Example
 *
 * Demonstrates integrating advanced reasoning and troubleshooting
 * capabilities into a chat interface using the AI SDK.
 */

'use client'

import { useMemo, useState, type FormEvent } from 'react'
import { useChat } from '@ai-sdk/react'
import { type UIMessagePart, type FileUIPart, type UITools } from 'ai'
import {
  ReasoningTrace,
  TroubleshootingWorkflow,
  type ReasoningTraceProps,
  type TroubleshootingState,
} from '@/features/chat/components/advanced'
import { Card } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { Brain, Wrench } from 'lucide-react'
import { ModelSelector } from './components/ModelSelector'
import { getAuthToken as getLocalAuthToken } from '@/services/auth/local-auth'
import { createBackendChatTransport } from '@/services/api/providers/unified-client'
import { cn } from '@/shared/lib/utils'
import {
  type ChatDataPart,
  type ChatDataTypes,
  type ChatUIMessage,
  type ToolDecisionRecord,
} from '@/shared/types/chat'

const buildAuthHeaders = async (): Promise<Record<string, string>> => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = await getLocalAuthToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const isStringArray = (value: unknown): string[] | null =>
  Array.isArray(value) && value.every((item) => typeof item === 'string') ? (value as string[]) : null

const isTextPart = (
  part: UIMessagePart<ChatDataTypes, UITools>,
): part is { type: 'text'; text: string } => part?.type === 'text' && typeof part.text === 'string'

const isFilePart = (
  part: UIMessagePart<ChatDataTypes, UITools>,
): part is FileUIPart => part?.type === 'file' && typeof part.url === 'string'

const toChatDataPart = (part: unknown): ChatDataPart | null => {
  if (!isRecord(part) || typeof part.type !== 'string') return null

  if (part.type === 'data') {
    const payload = isRecord(part.data) ? part.data : {}
    const innerType = typeof payload.type === 'string' ? (payload.type as string) : 'data'
    const innerData = 'data' in payload ? (payload.data as unknown) : part.data
    return { type: innerType, data: innerData }
  }

  if (part.type === 'data-timeline-step') {
    return { type: 'timeline-step', data: part.data }
  }

  return {
    type: part.type,
    data: part.data,
    transient: typeof part.transient === 'boolean' ? part.transient : undefined,
  }
}

const getDataParts = (message: ChatUIMessage): ChatDataPart[] => {
  const rawData = (message as ChatUIMessage & { data?: unknown }).data
  if (Array.isArray(rawData)) {
    const normalized = rawData
      .map(toChatDataPart)
      .filter((part): part is ChatDataPart => part !== null)
    if (normalized.length > 0) return normalized
  }

  const parts = Array.isArray(message.parts) ? message.parts : []
  return parts
    .map(toChatDataPart)
    .filter((part): part is ChatDataPart => part !== null)
}

const getMessageText = (message: ChatUIMessage): string => {
  const parts = Array.isArray(message.parts) ? message.parts : []
  return parts.filter(isTextPart).map((part) => part.text).join('')
}

const getFileParts = (message: ChatUIMessage): FileUIPart[] => {
  const parts = Array.isArray(message.parts) ? message.parts : []
  return parts.filter(isFilePart)
}

const parseReasoningThinkingTrace = (value: unknown): ReasoningTraceProps['reasoning'] | null => {
  if (!isRecord(value)) return null

  const thinkingSteps = Array.isArray(value.thinking_steps)
    ? value.thinking_steps
        .map((step) =>
          isRecord(step) && typeof step.thought === 'string'
            ? {
                phase: typeof step.phase === 'string' ? step.phase : 'UNKNOWN',
                thought: step.thought,
                confidence: typeof step.confidence === 'number' ? step.confidence : 0,
                evidence: Array.isArray(step.evidence) ? step.evidence.filter((item): item is string => typeof item === 'string') : undefined,
              }
            : null,
        )
        .filter((step): step is NonNullable<typeof step> => step !== null)
    : undefined

  const reasoning: ReasoningTraceProps['reasoning'] = {}

  if (typeof value.confidence === 'number') {
    reasoning.confidence_score = value.confidence
  }

  if (thinkingSteps && thinkingSteps.length > 0) {
    reasoning.thinking_steps = thinkingSteps
  }

  if (isRecord(value.query_analysis)) {
    reasoning.query_analysis = {
      intent: typeof value.query_analysis.intent === 'string' ? value.query_analysis.intent : undefined,
      problem_category: typeof value.query_analysis.problem_category === 'string' ? value.query_analysis.problem_category : undefined,
      emotional_state: typeof value.query_analysis.emotional_state === 'string' ? value.query_analysis.emotional_state : undefined,
      urgency_level: typeof value.query_analysis.urgency === 'number' ? value.query_analysis.urgency : undefined,
      technical_complexity: typeof value.query_analysis.complexity === 'number' ? value.query_analysis.complexity : undefined,
    }
  }

  if (isRecord(value.tool_decision) || typeof value.tool_decision === 'string') {
    const decisionRecord = isRecord(value.tool_decision) ? value.tool_decision : { decision: value.tool_decision }
    reasoning.tool_reasoning = {
      decision_type: typeof decisionRecord.decision === 'string' ? decisionRecord.decision : undefined,
      confidence: typeof decisionRecord.confidence === 'string' ? decisionRecord.confidence : undefined,
      reasoning: typeof decisionRecord.reasoning === 'string' ? decisionRecord.reasoning : undefined,
      recommended_tools: Array.isArray(decisionRecord.recommended_tools)
        ? decisionRecord.recommended_tools.filter((tool): tool is string => typeof tool === 'string')
        : undefined,
    }
  }

  if (Array.isArray(value.knowledge_gaps)) {
    reasoning.solution_mapping = {
      potential_solutions: [],
      knowledge_gaps: value.knowledge_gaps.filter((gap): gap is string => typeof gap === 'string'),
    }
  }

  return Object.keys(reasoning).length > 0 ? reasoning : null
}

const parseToolDecision = (value: unknown): ToolDecisionRecord | null => {
  if (!isRecord(value)) return null

  const decision: ToolDecisionRecord = {}

  if (typeof value.decision === 'string') {
    decision.decision = value.decision
  }

  if (typeof value.reasoning === 'string') {
    decision.reasoning = value.reasoning
  }

  if (Array.isArray(value.required_information)) {
    decision.required_information = value.required_information.filter((item): item is string => typeof item === 'string')
  }

  if (Object.keys(decision).length === 0) {
    return null
  }

  return decision
}

const parseTroubleshootingState = (value: unknown): TroubleshootingState | null =>
  (isRecord(value) ? (value as TroubleshootingState) : null)

const isReasoningData = (value: unknown): value is ReasoningTraceProps['reasoning'] => isRecord(value)

const normalizeTroubleshootingResult = (
  result: string,
): 'success' | 'failure' | 'partial' | 'skip' | 'inconclusive' => {
  switch (result) {
    case 'success':
    case 'failure':
    case 'partial':
    case 'skip':
      return result
    default:
      return 'inconclusive'
  }
}

export default function AdvancedChatExample() {
  const [reasoningData, setReasoningData] = useState<ReasoningTraceProps['reasoning'] | null>(null)
  const [troubleshootingData, setTroubleshootingData] = useState<TroubleshootingState | null>(null)
  const [showAdvancedFeatures, setShowAdvancedFeatures] = useState(true)

  const [provider, setProvider] = useState<'google' | 'openai'>('google')
  const [model, setModel] = useState<string>('gemini-2.5-flash')
  const [input, setInput] = useState('')
  const [toolDecision, setToolDecision] = useState<ToolDecisionRecord | null>(null)
  const [followUpQuestions, setFollowUpQuestions] = useState<string[] | null>(null)
  const [sessionId] = useState(() => crypto.randomUUID())

  const transport = useMemo(
    () =>
      createBackendChatTransport({
        provider,
        model,
        sessionId,
        getAuthToken: async () => getLocalAuthToken(),
      }),
    [provider, model, sessionId],
  )

  const { messages, sendMessage, status } = useChat<ChatUIMessage>({
    id: sessionId,
    transport,
    onFinish: ({ message }) => {
      const dataParts = getDataParts(message)

      const thinkingPart = dataParts.find((part) => part.type === 'data-thinking' || part.type === 'thinking')
      if (thinkingPart?.data) {
        const parsed = parseReasoningThinkingTrace(thinkingPart.data)
        if (parsed) setReasoningData(parsed)
      }

      const followupsPart = dataParts.find((part) => part.type === 'data-followups')
      setFollowUpQuestions(followupsPart ? isStringArray(followupsPart.data) : null)

      const toolPart = dataParts.find((part) => part.type === 'data-tool-result' || part.type === 'tool-result')
      setToolDecision(toolPart ? parseToolDecision(toolPart.data) : null)
    },
  })

  const isStreaming = status === 'streaming'

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!input.trim()) return

    sendMessage({ text: input })
    setInput('')
    setReasoningData(null)
    setTroubleshootingData(null)
    setToolDecision(null)
    setFollowUpQuestions(null)
  }

  const handleStepComplete = async (
    troubleshootingSession: string,
    result: 'success' | 'failure' | 'partial' | 'skip' | 'inconclusive',
    feedback?: string,
  ) => {
    try {
      const normalizedResult = result === 'inconclusive' ? 'partial' : result

      const response = await fetch('/api/v1/agent/advanced/troubleshooting/step', {
        method: 'POST',
        headers: await buildAuthHeaders(),
        body: JSON.stringify({
          session_id: troubleshootingSession,
          step_id: troubleshootingData?.current_step?.id ?? '',
          step_result: normalizedResult,
          customer_feedback: feedback,
        }),
      })

      if (!response.ok) return

      const payload = await response.json()
      const parsed = parseTroubleshootingState(payload)
      if (parsed) {
        setTroubleshootingData(parsed)
      }
    } catch (error) {
      console.error('Failed to complete troubleshooting step:', error)
    }
  }

  const handleEscalation = async (pathway: string) => {
    console.log('Escalating via pathway:', pathway)
    // Implement escalation logic as needed.
  }

  const triggerReasoningAnalysis = async (query: string) => {
    try {
      const response = await fetch('/api/v1/agent/advanced/reasoning', {
        method: 'POST',
        headers: await buildAuthHeaders(),
        body: JSON.stringify({
          query,
          provider,
          model,
          enable_chain_of_thought: true,
          enable_problem_solving: true,
          enable_tool_intelligence: true,
          enable_quality_assessment: true,
          thinking_budget: 50,
        }),
      })

      if (!response.ok) return

      const payload = await response.json()
      if (isReasoningData(payload)) {
        setReasoningData(payload)
      }
    } catch (error) {
      console.error('Failed to trigger reasoning analysis:', error)
    }
  }

  const startTroubleshooting = async (problem: string) => {
    try {
      let category = 'general_support'
      const lower = problem.toLowerCase()
      if (lower.includes('email')) category = 'technical_issue'
      else if (lower.includes('account')) category = 'account_setup'
      else if (lower.includes('how to')) category = 'feature_education'

      const response = await fetch('/api/v1/agent/advanced/troubleshooting/start', {
        method: 'POST',
        headers: await buildAuthHeaders(),
        body: JSON.stringify({
          problem_description: problem,
          problem_category: category,
          customer_technical_level: 3,
        }),
      })

      if (!response.ok) return

      const payload = await response.json()
      const parsed = parseTroubleshootingState(payload)
      if (parsed) {
        setTroubleshootingData(parsed)
      }
    } catch (error) {
      console.error('Failed to start troubleshooting:', error)
    }
  }

  return (
    <div className="flex h-screen">
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message, index) => {
            const content = getMessageText(message)
            const isAssistant = message.role === 'assistant'
            const isLastAssistant = isAssistant && index === messages.length - 1
            const fileParts = getFileParts(message)

            return (
              <div key={message.id ?? index} className="flex flex-col gap-2">
                <Card
                  className={cn(
                    'p-3',
                    message.role === 'user' ? 'ml-auto bg-blue-900/20' : 'bg-zinc-900/50',
                  )}
                >
                  <p className="text-sm whitespace-pre-wrap">{content}</p>
                  {message.role === 'user' && fileParts.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {fileParts.map((filePart, fileIndex) => (
                        <span
                          key={`${filePart.filename ?? fileIndex}`}
                          className="inline-flex items-center gap-2 rounded-full border border-border/40 bg-background/60 px-3 py-1 text-xs text-muted-foreground"
                        >
                          <span className="inline-block w-2 h-2 rounded-full bg-primary/60" />
                          {filePart.filename ?? 'attachment'}
                        </span>
                      ))}
                    </div>
                  )}
                </Card>

                {isLastAssistant && reasoningData && (
                  <ReasoningTrace reasoning={reasoningData} />
                )}

                {isLastAssistant && troubleshootingData && (
                  <TroubleshootingWorkflow
                    troubleshooting={troubleshootingData}
                    onStepExecute={(stepId, result, feedback) => {
                      const session = troubleshootingData.session_id ?? ''
                      const normalized = normalizeTroubleshootingResult(result)
                      handleStepComplete(session, normalized, feedback)
                      if (normalized === 'failure') {
                        handleEscalation('support_escalation')
                      }
                    }}
                  />
                )}

                {isLastAssistant && followUpQuestions && followUpQuestions.length > 0 && (
                  <Card className="bg-zinc-900/40 border border-zinc-800">
                    <div className="p-3 space-y-2">
                      <p className="text-xs font-semibold text-muted-foreground">Suggested follow-up questions</p>
                      <div className="flex flex-col gap-2">
                        {followUpQuestions.map((question, qIndex) => (
                          <Button
                            key={`${question}-${qIndex}`}
                            variant="secondary"
                            size="sm"
                            className="justify-start"
                            onClick={() => setInput(question)}
                          >
                            {question}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </Card>
                )}

                {isLastAssistant && toolDecision && (
                  <Card className="bg-zinc-900/40 border border-zinc-800">
                    <div className="p-3 space-y-1 text-sm text-muted-foreground">
                      <p className="text-xs font-semibold text-muted-foreground">Tool decision</p>
                      <p className="text-foreground font-medium">{toolDecision.decision ?? 'Decision unavailable'}</p>
                      {toolDecision.reasoning && <p>{toolDecision.reasoning}</p>}
                      {Array.isArray(toolDecision.required_information) && toolDecision.required_information.length > 0 && (
                        <ul className="list-disc list-inside text-xs space-y-1">
                          {toolDecision.required_information.map((info, infoIndex) => (
                            <li key={`${info}-${infoIndex}`}>{info}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </Card>
                )}
              </div>
            )
          })}
        </div>

        <div className="border-t p-4">
          <div className="flex justify-end mb-2">
            <ModelSelector
              provider={provider}
              model={model}
              onChangeProvider={(next) => {
                setProvider(next)
              }}
              onChangeModel={setModel}
              align="right"
            />
          </div>
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Type your message..."
              className="flex-1 px-3 py-2 rounded-lg bg-zinc-800 text-sm"
              disabled={isStreaming}
            />
            <Button type="submit" disabled={isStreaming}>
              Send
            </Button>
          </form>

          <div className="flex gap-2 mt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => input && triggerReasoningAnalysis(input)}
              disabled={!input || isStreaming}
            >
              <Brain className="h-3 w-3 mr-1" />
              Analyze with Reasoning
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => input && startTroubleshooting(input)}
              disabled={!input || isStreaming}
            >
              <Wrench className="h-3 w-3 mr-1" />
              Start Troubleshooting
            </Button>
          </div>
        </div>
      </div>

      {showAdvancedFeatures && (reasoningData || troubleshootingData) && (
        <div className="w-96 border-l p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold">Advanced Analysis</h3>
            <Button size="sm" variant="ghost" onClick={() => setShowAdvancedFeatures(false)}>
              Hide
            </Button>
          </div>

          <div className="space-y-4">
            {reasoningData && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">REASONING PIPELINE</h4>
                <ReasoningTrace reasoning={reasoningData} />
              </div>
            )}

            {troubleshootingData && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">TROUBLESHOOTING WORKFLOW</h4>
                <TroubleshootingWorkflow
                  troubleshooting={troubleshootingData}
                  onStepExecute={(stepId, result, feedback) => {
                    const session = troubleshootingData.session_id ?? ''
                    const normalized = normalizeTroubleshootingResult(result)
                    handleStepComplete(session, normalized, feedback)
                    if (normalized === 'failure') {
                      handleEscalation('support_escalation')
                    }
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
