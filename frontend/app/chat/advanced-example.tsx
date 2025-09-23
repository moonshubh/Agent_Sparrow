/**
 * Advanced Agent Integration Example
 * 
 * This file demonstrates how to integrate the advanced reasoning and
 * troubleshooting features into a chat interface using the AISDK.
 */

'use client'

import { useState, useEffect } from 'react'
import { useChat, type CreateUIMessage } from '@ai-sdk/react'
import { type UIMessage, DefaultChatTransport } from 'ai'
import { ReasoningTrace, TroubleshootingWorkflow } from '@/components/chat/advanced'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Brain, Wrench } from 'lucide-react'
import { ModelSelector } from './components/ModelSelector'
import { getAuthToken } from '@/lib/local-auth'

// Example: Handling advanced agent data parts in the chat interface
export default function AdvancedChatExample() {
  const [reasoningData, setReasoningData] = useState<any>(null)
  const [troubleshootingData, setTroubleshootingData] = useState<any>(null)
  const [showAdvancedFeatures, setShowAdvancedFeatures] = useState(true)

  // Provider/model selection for advanced reasoning requests
  const [provider, setProvider] = useState<'google' | 'openai'>('google')
  const [model, setModel] = useState<string>('gemini-2.5-flash')

  const [input, setInput] = useState('')

  const {
    messages,
    sendMessage,
    status,
  } = useChat({
    transport: new DefaultChatTransport({ api: '/api/chat' }),
    onFinish: (message) => {
      // Process data parts when message finishes
      const dataParts = (message as any).data
      if (dataParts) {
        // Look for reasoning data
        const reasoning = dataParts.find((d: any) => d.type === 'data-reasoning')
        if (reasoning) {
          setReasoningData(reasoning.data)
        }

        // Look for troubleshooting data
        const troubleshooting = dataParts.find((d: any) => d.type === 'data-troubleshooting')
        if (troubleshooting) {
          setTroubleshootingData(troubleshooting.data)
        }
      }
    },
  })

  const isLoading = status === 'streaming'

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim()) {
      sendMessage({ text: input })
      setInput('')
    }
  }

  // Handle troubleshooting step completion
  const handleStepComplete = async (
    sessionId: string,
    result: 'success' | 'failure' | 'inconclusive' | 'partial' | 'skip',
    feedback?: string
  ) => {
    try {
      // Map UI result to backend-accepted values
      const stepResult =
        result === 'inconclusive' ? 'partial' : (result as 'success' | 'failure' | 'partial' | 'skip')

      const response = await fetch('/api/v1/agent/advanced/troubleshooting/step', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getAuthToken()}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          step_id: troubleshootingData?.current_step?.id || '',
          step_result: stepResult,
          customer_feedback: feedback,
        }),
      })
      
      if (response.ok) {
        const data = await response.json()
        // Backend returns TroubleshootingResponse directly
        setTroubleshootingData(data)
      }
    } catch (error) {
      console.error('Failed to complete troubleshooting step:', error)
    }
  }

  // Handle escalation
  const handleEscalation = async (pathway: string) => {
    console.log('Escalating via pathway:', pathway)
    // Implement escalation logic here
  }

  // Example: Trigger advanced reasoning analysis
  const triggerReasoningAnalysis = async (query: string) => {
    try {
      const response = await fetch('/api/v1/agent/advanced/reasoning', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getAuthToken()}`,
        },
        body: JSON.stringify({
          query,
          provider,
          model,
          enable_chain_of_thought: true,
          enable_problem_solving: true,
          enable_tool_intelligence: true,
          enable_quality_assessment: true,
          // Backend ReasoningRequest limits thinking_budget to 1-100
          thinking_budget: 50,
        }),
      })
      
      if (response.ok) {
        const data = await response.json()
        // Backend returns ReasoningResponse directly
        setReasoningData(data)
      }
    } catch (error) {
      console.error('Failed to trigger reasoning analysis:', error)
    }
  }

  // Example: Start troubleshooting workflow
  const startTroubleshooting = async (problem: string) => {
    try {
      // Determine problem category based on keywords (simplified)
      let category = 'general_support'
      if (problem.toLowerCase().includes('email')) category = 'technical_issue'
      if (problem.toLowerCase().includes('account')) category = 'account_setup'
      if (problem.toLowerCase().includes('how to')) category = 'feature_education'
      
      const response = await fetch('/api/v1/agent/advanced/troubleshooting/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getAuthToken()}`,
        },
        body: JSON.stringify({
          problem_description: problem,
          problem_category: category,
          customer_technical_level: 3, // Medium
        }),
      })
      
      if (response.ok) {
        const data = await response.json()
        // Backend returns TroubleshootingResponse directly
        setTroubleshootingData(data)
      }
    } catch (error) {
      console.error('Failed to start troubleshooting:', error)
    }
  }

  return (
    <div className="flex h-screen">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message, index) => (
            <div key={index} className="flex flex-col gap-2">
              {/* Regular message display */}
              <Card className={cn(
                'p-3',
                message.role === 'user' ? 'ml-auto bg-blue-900/20' : 'bg-zinc-900/50'
              )}>
                <p className="text-sm">
                  {message.parts?.map((part, i) => {
                    if (part.type === 'text') {
                      return <span key={i}>{part.text}</span>
                    }
                    return null
                  })}
                </p>
              </Card>
              
              {/* Show reasoning trace after assistant messages if available */}
              {message.role === 'assistant' && index === messages.length - 1 && reasoningData && (
                <ReasoningTrace reasoning={reasoningData} />
              )}
              
              {/* Show troubleshooting workflow if active */}
              {message.role === 'assistant' && index === messages.length - 1 && troubleshootingData && (
                <TroubleshootingWorkflow
                  troubleshooting={troubleshootingData}
                  onStepExecute={(stepId, result, feedback) => {
                    // Pass-through to the same handler with session id
                    const sessionId = troubleshootingData?.session_id || ''
                    handleStepComplete(sessionId, result as any, feedback)
                  }}
                />
              )}
            </div>
          ))}
        </div>

        {/* Input Area */}
        <div className="border-t p-4">
          {/* Model selector for provider/model */}
          <div className="flex justify-end mb-2">
            <ModelSelector
              provider={provider}
              model={model}
              onChangeProvider={(p) => {
                setProvider(p)
                // Model will be set by ModelSelector component based on validation
              }}
              onChangeModel={(m) => setModel(m)}
              align="right"
            />
          </div>
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 px-3 py-2 rounded-lg bg-zinc-800 text-sm"
              disabled={isLoading}
            />
            <Button type="submit" disabled={isLoading}>
              Send
            </Button>
          </form>
          
          {/* Quick Actions */}
          <div className="flex gap-2 mt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => input && triggerReasoningAnalysis(input)}
              disabled={!input || isLoading}
            >
              <Brain className="h-3 w-3 mr-1" />
              Analyze with Reasoning
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => input && startTroubleshooting(input)}
              disabled={!input || isLoading}
            >
              <Wrench className="h-3 w-3 mr-1" />
              Start Troubleshooting
            </Button>
          </div>
        </div>
      </div>

      {/* Advanced Features Panel */}
      {showAdvancedFeatures && (reasoningData || troubleshootingData) && (
        <div className="w-96 border-l p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold">Advanced Analysis</h3>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowAdvancedFeatures(false)}
            >
              Hide
            </Button>
          </div>
          
          {/* Display advanced features in the sidebar */}
          <div className="space-y-4">
            {reasoningData && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                  REASONING PIPELINE
                </h4>
                <ReasoningTrace reasoning={reasoningData} />
              </div>
            )}
            
            {troubleshootingData && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                  TROUBLESHOOTING WORKFLOW
                </h4>
                <TroubleshootingWorkflow
                  troubleshooting={troubleshootingData}
                  onStepExecute={(stepId, result, feedback) => {
                    const sessionId = troubleshootingData?.session_id || ''
                    handleStepComplete(sessionId, result as any, feedback)
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


// Utility function (add to your utils)
function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ')
}