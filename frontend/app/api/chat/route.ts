import { NextRequest } from 'next/server'
import { z } from 'zod'
import { streamText, createUIMessageStream, createUIMessageStreamResponse, convertToModelMessages, type UIMessage, type UIMessageChunk } from 'ai'
import { createGoogleGenerativeAI } from '@ai-sdk/google'
import { createOpenAI } from '@ai-sdk/openai'
import { getApiUrl } from '@/lib/utils/environment'
import { getAPIKeyWithFallback } from '@/lib/api/api-key-service'
import { APIKeyType } from '@/lib/api-keys'
import { rateLimitApi } from '@/lib/api/rateLimitApi'
import { supabase } from '@/lib/supabase-browser'
import { getAuthToken } from '@/lib/local-auth'

export const runtime = 'nodejs'

// Constants for request validation and limits
const MAX_REQUEST_SIZE = 1024 * 1024 // 1MB maximum request size
const MAX_MESSAGE_COUNT = 50 // Maximum number of messages in history
const MAX_MESSAGE_LENGTH = 50000 // Maximum length per message
const PERSIST_BUFFER_SIZE = 200 // Characters to buffer before persisting
const INITIAL_PERSIST_SIZE = 32 // Initial characters before creating message

// Environment fallback keys
const envGoogleApiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_GENERATIVE_AI_API_KEY || ''
const envOpenaiApiKey = process.env.OPENAI_API_KEY || ''

const kbSearchSchema = z.object({
  query: z.string().min(1).max(1000),
  limit: z.number().int().min(1).max(20).optional(),
  minConfidence: z.number().min(0).max(1).optional(),
})

const logAnalysisSchema = z.object({
  logText: z.string().min(10).max(500000), // Max 500KB for log analysis
})

const reasoningAnalysisSchema = z.object({
  query: z.string().min(1).max(4000),
  enableChainOfThought: z.boolean().optional(),
  enableProblemSolving: z.boolean().optional(),
  enableToolIntelligence: z.boolean().optional(),
  enableQualityAssessment: z.boolean().optional(),
  enableSelfCritique: z.boolean().optional(),
  thinkingBudget: z.number().int().min(-1).max(24576).optional(),
})

const troubleshootingSchema = z.object({
  problemDescription: z.string().min(1).max(2000),
  problemCategory: z.enum([
    'technical_issue',
    'account_setup',
    'feature_education',
    'billing_inquiry',
    'performance_optimization',
    'troubleshooting',
    'general_support'
  ]),
  customerTechnicalLevel: z.number().int().min(1).max(5).optional(),
})

const SYSTEM_PROMPT = `You are Agent Sparrow, a professional customer support assistant for Mailbird.
- Be concise, accurate, and empathetic.
- Use tools when you need grounded knowledge or log analysis.
- IMPORTANT: When a log file is attached to the conversation, you MUST use the logAnalysis tool to analyze it before responding.
- If information is uncertain, say so and offer next steps.
- At the end of your reasoning, internally derive 2-4 follow-up questions and a brief high-level thinking trace (no secrets).`

// Mutex for preventing race conditions in message persistence
class MessagePersistenceMutex {
  private locked = false
  private queue: (() => Promise<void>)[] = []

  async acquire(): Promise<() => void> {
    while (this.locked) {
      await new Promise(resolve => setTimeout(resolve, 10))
    }
    this.locked = true
    return () => {
      this.locked = false
      const next = this.queue.shift()
      if (next) next()
    }
  }
}

const persistenceMutex = new MessagePersistenceMutex()

// Helper to validate request size
function validateRequestSize(body: any): { valid: boolean; error?: string } {
  try {
    const bodyStr = JSON.stringify(body)
    if (bodyStr.length > MAX_REQUEST_SIZE) {
      return { 
        valid: false, 
        error: `Request too large (${Math.round(bodyStr.length / 1024)}KB). Maximum size is ${MAX_REQUEST_SIZE / 1024}KB.`
      }
    }
    return { valid: true }
  } catch {
    return { valid: false, error: 'Invalid request format' }
  }
}

// Helper to validate messages
function validateMessages(messages: any[]): { valid: boolean; error?: string } {
  if (!Array.isArray(messages)) {
    return { valid: false, error: 'Messages must be an array' }
  }
  
  if (messages.length > MAX_MESSAGE_COUNT) {
    return { 
      valid: false, 
      error: `Too many messages (${messages.length}). Maximum is ${MAX_MESSAGE_COUNT}.`
    }
  }
  
  for (const msg of messages) {
    // Handle undefined, null, or other content types
    let content: string
    if (msg.content === undefined || msg.content === null) {
      content = ''
    } else if (typeof msg.content === 'string') {
      content = msg.content
    } else {
      content = JSON.stringify(msg.content)
    }
    
    if (content.length > MAX_MESSAGE_LENGTH) {
      return { 
        valid: false, 
        error: `Message too long (${content.length} chars). Maximum is ${MAX_MESSAGE_LENGTH}.`
      }
    }
  }
  
  return { valid: true }
}

// Unified rate limiting for all providers
async function checkRateLimits(
  provider: 'google' | 'openai',
  model: string,
  authToken: string | null
): Promise<{ allowed: boolean; error?: string; retryAfter?: number }> {
  try {
    // Get user ID if authenticated
    let userId: string | undefined
    if (authToken) {
      const { data: { user } } = await supabase.auth.getUser(authToken)
      userId = user?.id
    }

    // Map models to rate limit names
    let rateLimitModel: string
    if (provider === 'google') {
      rateLimitModel = model.includes('flash') ? 'gemini-2.5-flash' : 'gemini-2.5-pro'
    } else {
      // OpenAI models
      rateLimitModel = model.includes('gpt-4') ? 'gpt-4' : 'gpt-3.5'
    }
    
    // Check rate limits
    const rateLimitCheck = await rateLimitApi.checkRateLimit(rateLimitModel as any)
    
    if (!rateLimitCheck.allowed) {
      return {
        allowed: false,
        error: `Rate limit exceeded for ${rateLimitModel}`,
        retryAfter: rateLimitCheck.retry_after || 60
      }
    }
    
    return { allowed: true }
  } catch (error) {
    // Log but don't block on rate limit check failures
    if (process.env.NODE_ENV === 'development') {
      console.warn('Rate limit check failed:', error instanceof Error ? error.message : 'Unknown error')
    }
    // Allow request to proceed if rate limit check fails
    return { allowed: true }
  }
}

export async function POST(req: NextRequest) {
  const apiBase = getApiUrl()
  const authHeader = req.headers.get('authorization') || undefined
  const authToken = authHeader?.replace('Bearer ', '') || null

  let body: any
  try {
    body = await req.json()
  } catch (error) {
    return new Response('Invalid JSON in request body', { status: 400 })
  }

  // Validate request size
  const sizeValidation = validateRequestSize(body)
  if (!sizeValidation.valid) {
    return new Response(sizeValidation.error, { status: 400 })
  }

  // Debug logging (development only, no PII)
  if (process.env.NODE_ENV === 'development') {
    console.log('AI Route: Request received', {
      hasMessages: Array.isArray(body?.messages),
      messageCount: body?.messages?.length || 0,
      provider: body?.data?.modelProvider || 'google'
    })
  }

  const uiMessages = Array.isArray(body?.messages) ? body.messages : []
  
  // Validate messages
  const messageValidation = validateMessages(uiMessages)
  if (!messageValidation.valid) {
    return new Response(messageValidation.error, { status: 400 })
  }

  // Convert to model messages
  let modelMessages: Array<{ role: 'user' | 'assistant' | 'system'; content: any }>
  try {
    const first = uiMessages[0]
    if (first && Array.isArray((first as any).parts)) {
      modelMessages = convertToModelMessages(uiMessages as UIMessage[])
    } else {
      modelMessages = uiMessages as any
    }
  } catch (error) {
    return new Response('Failed to parse messages', { status: 400 })
  }

  const attachedLogText: string | undefined = body?.data?.attachedLogText
  const modelProvider: 'google' | 'openai' | undefined = body?.data?.modelProvider
  const modelName: string | undefined = body?.data?.model
  const sessionId: string | number | undefined = body?.data?.sessionId
  const useServerMemory: boolean | undefined = body?.data?.useServerMemory

  // Validate attached log text size
  if (attachedLogText && attachedLogText.length > 500000) {
    return new Response('Attached log text too large. Maximum size is 500KB.', { status: 400 })
  }

  // Prepare model with user or fallback API keys
  const provider = modelProvider || 'google'
  const selectedModel = modelName || (provider === 'openai' ? 'gpt-4o-mini' : 'gemini-2.5-flash')
  
  // Check rate limits for ALL providers
  const rateLimitResult = await checkRateLimits(provider, selectedModel, authToken)
  if (!rateLimitResult.allowed) {
    return new Response(
      JSON.stringify({ error: 'Rate limit exceeded' }),
      { status: 429, headers: { 'Content-Type': 'application/json' } }
    )
  }
  
  // Track usage BEFORE making the API call (reservation pattern)
  let usageTracked = false
  if (authToken && provider === 'google') {
    try {
      const { data: { user } } = await supabase.auth.getUser(authToken)
      if (user) {
        const today = new Date().toISOString().split('T')[0]
        // Increment usage counter BEFORE the API call (reservation)
        await supabase.rpc('increment_api_usage', {
          p_user_id: user.id,
          p_model: selectedModel,
          p_date: today
        })
        usageTracked = true
      }
    } catch (error) {
      // Don't block on usage tracking
      if (process.env.NODE_ENV === 'development') {
        console.warn('Failed to track API usage:', error)
      }
    }
  }
  
  // Get API keys
  let googleApiKey: string | null = null
  let openaiApiKey: string | null = null
  
  if (provider === 'google') {
    // Debug: Log environment variable
    console.log('DEBUG: envGoogleApiKey from env:', envGoogleApiKey ? `${envGoogleApiKey.substring(0, 10)}...` : 'NOT SET')
    console.log('DEBUG: GEMINI_API_KEY env var:', process.env.GEMINI_API_KEY ? `${process.env.GEMINI_API_KEY.substring(0, 10)}...` : 'NOT SET')
    
    googleApiKey = await getAPIKeyWithFallback(authToken, APIKeyType.GEMINI, envGoogleApiKey)
    
    // Debug: Log the actual key being used
    console.log('DEBUG: Final googleApiKey:', googleApiKey ? `${googleApiKey.substring(0, 10)}...` : 'NOT SET')
    
    if (!googleApiKey) {
      return new Response(
        'Gemini API key missing. Please configure your API key in settings or contact your administrator.',
        { status: 400 }
      )
    }
    if (process.env.NODE_ENV === 'development') {
      console.log('Using Gemini API key:', googleApiKey.startsWith('AIza') ? 'User key' : 'Environment fallback')
    }
  }
  
  if (provider === 'openai') {
    // For OpenAI, try to get user key first, then fallback to env
    openaiApiKey = await getAPIKeyWithFallback(authToken, APIKeyType.OPENAI as any, envOpenaiApiKey)
    if (!openaiApiKey) {
      return new Response(
        'OpenAI API key missing. Please configure your API key in settings or contact your administrator.',
        { status: 400 }
      )
    }
  }
  
  // Create model instances
  const google = provider === 'google' && googleApiKey ? createGoogleGenerativeAI({ apiKey: googleApiKey }) : null
  const openai = provider === 'openai' && openaiApiKey ? createOpenAI({ apiKey: openaiApiKey }) : null
  const model = provider === 'openai' && openai ? openai(selectedModel) : google ? google(selectedModel) : null
  
  if (!model) {
    return new Response(
      'Failed to initialize AI model. Please check your API key configuration.',
      { status: 500 }
    )
  }

  // Optional server memory: fetch prior messages from backend chat session
  let history: Array<{ role: 'user' | 'assistant' | 'system'; content: string }> = []
  if (useServerMemory && sessionId) {
    try {
      const res = await fetch(`${apiBase}/api/v1/chat-sessions/${sessionId}?include_messages=true`, {
        headers: {
          'Content-Type': 'application/json',
          ...(authHeader ? { Authorization: authHeader } : {}),
        },
        signal: AbortSignal.timeout(5000) // 5 second timeout
      })
      if (res.ok) {
        const json = await res.json()
        const msgs = (json?.messages || [])
          .map((m: any) => ({
            role: m.message_type === 'assistant' ? 'assistant' : m.message_type,
            content: m.content as string,
          }))
          .filter((m: any) => m.role === 'user' || m.role === 'assistant' || m.role === 'system')
        // Limit to last 20 to control context length
        history = msgs.slice(-20)
      }
    } catch (error) {
      // Log error but continue without history
      if (process.env.NODE_ENV === 'development') {
        console.error('Failed to fetch session history:', error instanceof Error ? error.message : 'Unknown error')
      }
    }
  }

  try {
    // Collect tool outputs for structured UI cards
    const kbCollected: Array<{ results: any[]; total_results: number }> = []
    const logCollected: Array<any> = []
    const reasoningCollected: Array<any> = []
    const troubleshootingCollected: Array<any> = []
    let accumulatedText = ''
    const shouldUseTools = Boolean(attachedLogText)
    
    // When a log is attached, prepend instruction to the last user message
    if (attachedLogText && modelMessages.length > 0) {
      const lastMessage = modelMessages[modelMessages.length - 1]
      if (lastMessage.role === 'user' && typeof lastMessage.content === 'string') {
        lastMessage.content = `[A log file has been attached. Please analyze it using the logAnalysis tool before responding.]\n\n${lastMessage.content}`
      }
    }
    
    const result = await streamText({
      model,
      system: SYSTEM_PROMPT,
      messages: [...history, ...modelMessages],
      tools: {
        kbSearch: {
          description: 'Search approved FeedMe examples and knowledge base.',
          parameters: kbSearchSchema,
          execute: async ({ query, limit = 8, minConfidence = 0.7 }) => {
            try {
              const res = await fetch(`${apiBase}/api/v1/feedme/search`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(authHeader ? { Authorization: authHeader } : {}),
                },
                body: JSON.stringify({ query, limit, min_confidence: minConfidence }),
                signal: AbortSignal.timeout(10000) // 10 second timeout
              })
              if (!res.ok) {
                return { results: [], total_results: 0, error: `kbSearch unavailable: ${res.status}` }
              }
              const json = await res.json()
              const mapped = {
                results: (json?.results || []).map((r: any) => ({
                  example_id: r.example_id,
                  question: r.question,
                  answer: r.answer,
                  confidence: r.confidence,
                  conversation_title: r.conversation_title,
                })),
                total_results: json?.total_results ?? 0,
              }
              kbCollected.push(mapped)
              return mapped
            } catch (err) {
              return { results: [], total_results: 0, error: 'kbSearch error' }
            }
          },
        },
        logAnalysis: {
          description: 'Analyze a log file text for issues and solutions.',
          parameters: logAnalysisSchema,
          execute: async ({ logText }) => {
            try {
              const textToUse = logText || attachedLogText
              if (!textToUse) {
                return { overall_summary: 'No log provided', identified_issues: [], proposed_solutions: [] }
              }
              const res = await fetch(`${apiBase}/api/v1/agent/logs`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(authHeader ? { Authorization: authHeader } : {}),
                },
                body: JSON.stringify({ content: textToUse }),
                signal: AbortSignal.timeout(30000) // 30 second timeout for log analysis
              })
              if (!res.ok) {
                return { overall_summary: 'Log analysis service unavailable', identified_issues: [], proposed_solutions: [] }
              }
              const json = await res.json()
              const mapped = {
                overall_summary: json?.overall_summary,
                health_status: json?.health_status,
                priority_concerns: json?.priority_concerns,
                identified_issues: (json?.identified_issues || []).slice(0, 5),
                proposed_solutions: (json?.proposed_solutions || []).slice(0, 5),
              }
              logCollected.push(mapped)
              return mapped
            } catch (err) {
              return { overall_summary: 'Log analysis error', identified_issues: [], proposed_solutions: [] }
            }
          },
        },
        reasoningAnalysis: {
          description: 'Perform advanced reasoning analysis with 6-phase pipeline to understand complex queries',
          parameters: reasoningAnalysisSchema,
          execute: async ({ query, enableChainOfThought = true, enableProblemSolving = true, enableToolIntelligence = true, enableQualityAssessment = true, enableSelfCritique = true, thinkingBudget }) => {
            try {
              const res = await fetch(`${apiBase}/api/v1/agent/advanced/reasoning`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(authHeader ? { Authorization: authHeader } : {}),
                },
                body: JSON.stringify({
                  query,
                  enable_chain_of_thought: enableChainOfThought,
                  enable_problem_solving: enableProblemSolving,
                  enable_tool_intelligence: enableToolIntelligence,
                  enable_quality_assessment: enableQualityAssessment,
                  enable_self_critique: enableSelfCritique,
                  thinking_budget: thinkingBudget,
                  session_id: sessionId
                }),
                signal: AbortSignal.timeout(30000) // 30 second timeout
              })
              if (!res.ok) {
                return { success: false, error: `Reasoning analysis unavailable: ${res.status}` }
              }
              const json = await res.json()
              const reasoning = json?.reasoning_state || {}
              reasoningCollected.push(reasoning)
              return {
                success: true,
                confidence: reasoning.overall_confidence,
                emotional_state: reasoning.emotional_state,
                problem_category: reasoning.problem_category,
                complexity_score: reasoning.complexity_score,
                thinking_steps: reasoning.thinking_steps?.slice(0, 5),
                tool_decision: reasoning.tool_decision,
                solution_candidates: reasoning.solution_candidates?.slice(0, 3),
                is_escalated: reasoning.is_escalated,
                escalation_reason: reasoning.escalation_reason
              }
            } catch (err) {
              return { success: false, error: 'Reasoning analysis error' }
            }
          },
        },
        startTroubleshooting: {
          description: 'Start a structured 7-phase troubleshooting workflow with diagnostic steps',
          parameters: troubleshootingSchema,
          execute: async ({ problemDescription, problemCategory, customerTechnicalLevel = 3 }) => {
            try {
              const res = await fetch(`${apiBase}/api/v1/agent/advanced/troubleshooting/start`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(authHeader ? { Authorization: authHeader } : {}),
                },
                body: JSON.stringify({
                  problem_description: problemDescription,
                  problem_category: problemCategory,
                  customer_technical_level: customerTechnicalLevel,
                  enable_adaptive_workflows: true,
                  enable_progressive_complexity: true,
                  enable_verification_checkpoints: true,
                  enable_automatic_escalation: true,
                  session_id: sessionId
                }),
                signal: AbortSignal.timeout(20000) // 20 second timeout
              })
              if (!res.ok) {
                return { success: false, error: `Troubleshooting unavailable: ${res.status}` }
              }
              const json = await res.json()
              const troubleshooting = json?.troubleshooting_state || {}
              troubleshootingCollected.push(troubleshooting)
              return {
                success: true,
                session_id: json?.session_id,
                current_phase: troubleshooting.current_phase,
                workflow_name: troubleshooting.workflow_name,
                workflow_description: troubleshooting.workflow_description,
                total_steps: troubleshooting.total_steps,
                current_step: troubleshooting.current_step,
                next_steps: troubleshooting.next_steps?.slice(0, 3),
                verification_checkpoints: troubleshooting.verification_checkpoints?.slice(0, 3),
                customer_technical_level: troubleshooting.customer_technical_level
              }
            } catch (err) {
              return { success: false, error: 'Troubleshooting initialization error' }
            }
          },
        },
      },
      toolChoice: shouldUseTools ? 'auto' : 'none',
      includeRawChunks: false,
      onChunk: (part) => {
        if (part.type === 'text-delta' && typeof part.text === 'string') {
          accumulatedText += part.text
        }
      },
    })

    // Build base UI stream for the model output
    const baseStream = result.toUIMessageStream<UIMessage>({
      originalMessages: uiMessages,
      sendReasoning: true,
      sendSources: false,
    })

    // Tee the stream so we can both forward to client and analyze to emit data parts
    const [forwardStream, analyzeStream] = baseStream.tee()

    // If sessionId provided, persist the last user message immediately
    if (sessionId) {
      try {
        const lastUser = modelMessages.filter((m) => m.role === 'user').slice(-1)[0]
        let textOnly = ''
        // If content is an array of parts, try to extract text
        if (Array.isArray((lastUser as any)?.content)) {
          textOnly = ((lastUser as any).content || [])
            .filter((p: any) => p?.type === 'text' && typeof p.text === 'string')
            .map((p: any) => p.text)
            .join('')
        } else if (typeof (lastUser as any)?.content === 'string') {
          textOnly = (lastUser as any).content
        }
        if (textOnly) {
          await fetch(`${apiBase}/api/v1/chat-sessions/${sessionId}/messages`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(authHeader ? { Authorization: authHeader } : {}),
            },
            body: JSON.stringify({ content: textOnly, message_type: 'user' }),
            signal: AbortSignal.timeout(5000)
          })
        }
      } catch (error) {
        if (process.env.NODE_ENV === 'development') {
          console.error('Failed to persist user message:', error instanceof Error ? error.message : 'Unknown error')
        }
      }
    }

    // Create a composite UI stream that merges model UI chunks and our data parts
    const uiStream = createUIMessageStream<UIMessage>({
      originalMessages: uiMessages,
      async execute({ writer }) {
        // Pass-through model UI chunks
        writer.merge(forwardStream)

        // Analyze chunks to emit data parts periodically
        const reader = analyzeStream.getReader()
        let textAcc = ''
        let lastEmitLen = 0
        let assistantMsgId: number | null = null
        let persistBuffer = ''
        
        // Use mutex to prevent race conditions in persistence
        const persistMessage = async (content: string, isCreate: boolean) => {
          const release = await persistenceMutex.acquire()
          try {
            if (isCreate && !assistantMsgId) {
              const res = await fetch(`${apiBase}/api/v1/chat-sessions/${sessionId}/messages`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(authHeader ? { Authorization: authHeader } : {}),
                },
                body: JSON.stringify({
                  content,
                  message_type: 'assistant',
                  agent_type: 'primary',
                }),
                signal: AbortSignal.timeout(5000)
              })
              if (res.ok) {
                const msg = await res.json()
                assistantMsgId = msg.id
              }
            } else if (!isCreate && assistantMsgId) {
              await fetch(`${apiBase}/api/v1/chat-sessions/${sessionId}/messages/${assistantMsgId}/append`, {
                method: 'PATCH',
                headers: {
                  'Content-Type': 'application/json',
                  ...(authHeader ? { Authorization: authHeader } : {}),
                },
                body: JSON.stringify({ delta: content }),
                signal: AbortSignal.timeout(5000)
              })
            }
          } catch (error) {
            if (process.env.NODE_ENV === 'development') {
              console.error('Message persistence error:', error instanceof Error ? error.message : 'Unknown error')
            }
          } finally {
            release()
          }
        }
        
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const chunk = value as UIMessageChunk
            if (chunk.type === 'text-delta') {
              textAcc += chunk.delta || ''
              if (textAcc.length - lastEmitLen >= 200) {
                lastEmitLen = textAcc.length
                writer.write({ type: 'data-followups', data: deriveFollowUps(textAcc), transient: true } as any)
              }
              // Incremental persistence with mutex protection
              if (sessionId) {
                persistBuffer += chunk.delta || ''
                if (!assistantMsgId && persistBuffer.length >= INITIAL_PERSIST_SIZE) {
                  await persistMessage(persistBuffer, true)
                  persistBuffer = ''
                } else if (assistantMsgId && persistBuffer.length >= PERSIST_BUFFER_SIZE) {
                  await persistMessage(persistBuffer, false)
                  persistBuffer = ''
                }
              }
            } else if (chunk.type === 'text-end') {
              // Emit final data parts on end
              writer.write({ type: 'data-followups', data: deriveFollowUps(textAcc) } as any)
              writer.write({ type: 'data-thinking', data: deriveThinkingTrace(textAcc) } as any)
              // Emit structured tool results if present
              if (kbCollected.length > 0) {
                const merged = kbCollected[kbCollected.length - 1]
                writer.write({ type: 'data-kb', data: merged } as any)
              }
              if (logCollected.length > 0) {
                const latest = logCollected[logCollected.length - 1]
                writer.write({ type: 'data-log-analysis', data: latest } as any)
              }
              if (reasoningCollected.length > 0) {
                const latest = reasoningCollected[reasoningCollected.length - 1]
                writer.write({ type: 'data-reasoning', data: latest } as any)
              }
              if (troubleshootingCollected.length > 0) {
                const latest = troubleshootingCollected[troubleshootingCollected.length - 1]
                writer.write({ type: 'data-troubleshooting', data: latest } as any)
              }
              // Flush remaining persistence buffer
              if (sessionId && persistBuffer.length > 0) {
                if (assistantMsgId) {
                  await persistMessage(persistBuffer, false)
                } else {
                  await persistMessage(textAcc, true)
                }
                persistBuffer = ''
              }
            }
          }
        } catch (error) {
          if (process.env.NODE_ENV === 'development') {
            console.error('Stream processing error:', error instanceof Error ? error.message : 'Unknown error')
          }
        }
      },
      onFinish: undefined,
    })

    // Return the merged UI stream as a Response
    return createUIMessageStreamResponse({
      stream: uiStream,
    })
  } catch (err: any) {
    const message = err?.message || 'Internal error'
    if (process.env.NODE_ENV === 'development') {
      console.error('Request processing error:', message)
    }
    return new Response(message, { status: 500 })
  }
}

function deriveFollowUps(answer: string): string[] {
  const qs: string[] = []
  if (/password|login|auth/i.test(answer)) qs.push('Would you like help verifying your account settings?')
  if (/error|issue|problem|fail/i.test(answer)) qs.push('Can you share the exact error message or a screenshot?')
  if (qs.length < 2) qs.push('Do you want me to go deeper or provide step-by-step fixes?')
  return Array.from(new Set(qs)).slice(0, 4)
}

function deriveThinkingTrace(answer: string) {
  return {
    confidence: 0.7,
    thinking_steps: [
      { phase: 'QUERY_ANALYSIS', thought: 'Parsed user intent and context.', confidence: 0.7 },
      { phase: 'RESPONSE_STRATEGY', thought: 'Composed concise, actionable guidance.', confidence: 0.7 },
    ],
    tool_decision: 'NO_TOOLS_NEEDED',
    tool_confidence: 'MEDIUM',
  }
}
