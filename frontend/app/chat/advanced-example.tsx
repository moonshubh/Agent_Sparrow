/**
 * Advanced Agent Integration Example
 * 
 * This file demonstrates how to integrate the advanced reasoning and
 * troubleshooting features into a chat interface using the AISDK.
 */

'use client'

import { useState, useEffect } from 'react'
import { useChat } from 'ai/react'
import { ReasoningTrace, TroubleshootingWorkflow } from '@/components/chat/advanced'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Brain, Wrench } from 'lucide-react'

// Example: Handling advanced agent data parts in the chat interface
export default function AdvancedChatExample() {
  const [reasoningData, setReasoningData] = useState<any>(null)
  const [troubleshootingData, setTroubleshootingData] = useState<any>(null)
  const [showAdvancedFeatures, setShowAdvancedFeatures] = useState(true)

  const {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    data, // This contains the data parts from the stream
    isLoading,
  } = useChat({
    api: '/api/chat',
    onFinish: (message, options) => {
      // Process data parts when message finishes
      if (options?.data) {
        // Look for reasoning data
        const reasoning = options.data.find((d: any) => d.type === 'data-reasoning')
        if (reasoning) {
          setReasoningData(reasoning.data)
        }
        
        // Look for troubleshooting data
        const troubleshooting = options.data.find((d: any) => d.type === 'data-troubleshooting')
        if (troubleshooting) {
          setTroubleshootingData(troubleshooting.data)
        }
      }
    },
  })

  // Handle troubleshooting step completion
  const handleStepComplete = async (
    sessionId: string,
    result: 'success' | 'failure' | 'inconclusive',
    feedback?: string
  ) => {
    try {
      const response = await fetch('/api/v1/agent/advanced/troubleshooting/step', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getAuthToken()}`, // Your auth token function
        },
        body: JSON.stringify({
          session_id: sessionId,
          step_id: troubleshootingData?.current_step?.step_id || '',
          result,
          customer_feedback: feedback,
        }),
      })
      
      if (response.ok) {
        const data = await response.json()
        setTroubleshootingData(data.troubleshooting_state)
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
          enable_chain_of_thought: true,
          enable_problem_solving: true,
          enable_tool_intelligence: true,
          enable_quality_assessment: true,
          enable_self_critique: true,
          thinking_budget: 8192, // Medium complexity
        }),
      })
      
      if (response.ok) {
        const data = await response.json()
        setReasoningData(data.reasoning_state)
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
        setTroubleshootingData(data.troubleshooting_state)
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
                <p className="text-sm">{message.content}</p>
              </Card>
              
              {/* Show reasoning trace after assistant messages if available */}
              {message.role === 'assistant' && index === messages.length - 1 && reasoningData && (
                <ReasoningTrace reasoning={reasoningData} />
              )}
              
              {/* Show troubleshooting workflow if active */}
              {message.role === 'assistant' && index === messages.length - 1 && troubleshootingData && (
                <TroubleshootingWorkflow
                  troubleshooting={troubleshootingData}
                  onStepComplete={handleStepComplete}
                  onEscalate={handleEscalation}
                />
              )}
            </div>
          ))}
        </div>

        {/* Input Area */}
        <div className="border-t p-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              value={input}
              onChange={handleInputChange}
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
                  onStepComplete={handleStepComplete}
                  onEscalate={handleEscalation}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Helper function to get auth token (implement based on your auth setup)
async function getAuthToken(): Promise<string> {
  // This should return the current user's auth token
  // Example: return await supabase.auth.getSession()?.access_token
  return ''
}

// Utility function (add to your utils)
function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ')
}