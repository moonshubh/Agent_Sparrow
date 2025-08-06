"use client"

import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ChevronRight, MessageCircle, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { UnifiedMessage } from '@/hooks/useUnifiedChat'

interface FollowUpQuestionsProps {
  messages: UnifiedMessage[]
  onQuestionClick: (question: string) => void
  isProcessing: boolean
  className?: string
}

export function FollowUpQuestions({ 
  messages, 
  onQuestionClick, 
  isProcessing,
  className 
}: FollowUpQuestionsProps) {
  const [availableQuestions, setAvailableQuestions] = useState<string[]>([])
  const [usedQuestions, setUsedQuestions] = useState<Set<string>>(new Set())
  const [sessionQuestionCount, setSessionQuestionCount] = useState(0)

  useEffect(() => {
    // Optimized performance: Single pass through messages with Map for O(1) lookups
    const sessionUsedQuestions = new Set<string>()
    const agentQuestionMap = new Map<string, number>() // Map question to agent message index
    let totalUsed = 0
    let latestAgentQuestions: string[] = []
    
    // Single pass through messages
    messages.forEach((message, index) => {
      if (message.type === 'agent' && message.metadata?.followUpQuestions) {
        // Track all follow-up questions from agent messages
        message.metadata.followUpQuestions.forEach(q => {
          agentQuestionMap.set(q, index)
        })
        // Keep track of latest agent's questions
        latestAgentQuestions = message.metadata.followUpQuestions
      } else if (message.type === 'user') {
        // Check if this user message matches any previous agent's follow-up question
        if (agentQuestionMap.has(message.content)) {
          const agentIndex = agentQuestionMap.get(message.content)!
          // Ensure the agent message came before this user message
          if (agentIndex < index) {
            sessionUsedQuestions.add(message.content)
            totalUsed++
          }
        }
      }
    })
    
    setUsedQuestions(sessionUsedQuestions)
    setSessionQuestionCount(totalUsed)
    
    // Filter out used questions from the latest agent's questions
    const availableQs = latestAgentQuestions.filter(q => !sessionUsedQuestions.has(q))
    setAvailableQuestions(availableQs)
  }, [messages])

  const handleQuestionClick = (question: string) => {
    if (isProcessing || sessionQuestionCount >= 5) return
    
    // Mark question as used
    setUsedQuestions(prev => new Set(prev).add(question))
    
    // Increment session count
    setSessionQuestionCount(prev => prev + 1)
    
    // Send the question
    onQuestionClick(question)
  }

  // Don't show if no questions available or already used 5 questions
  if (availableQuestions.length === 0 || sessionQuestionCount >= 5 || isProcessing) {
    return null
  }

  const remainingQuestions = 5 - sessionQuestionCount

  return (
    <Card className={cn(
      "border-[var(--mailbird-blue-light)]/20 bg-gradient-to-br from-[var(--mailbird-blue-light)]/5 to-transparent p-4",
      className
    )}>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-[var(--mailbird-blue-light)]" aria-hidden="true" />
            <h3 className="text-sm font-medium" id="follow-up-questions-heading">Suggested Follow-up Questions</h3>
          </div>
          <span className="text-xs text-muted-foreground" aria-live="polite" role="status">
            {remainingQuestions} remaining
          </span>
        </div>
        
        <div className="grid gap-2" role="group" aria-labelledby="follow-up-questions-heading">
          {availableQuestions.slice(0, Math.min(3, remainingQuestions)).map((question, index) => (
            <Button
              key={`${question}-${index}`}
              variant="outline"
              size="sm"
              className={cn(
                "justify-start text-left h-auto py-2 px-3 text-sm",
                "hover:bg-[var(--mailbird-blue-light)]/10 hover:border-[var(--mailbird-blue-light)]/30",
                "focus:outline-none focus:ring-2 focus:ring-[var(--mailbird-blue-light)] focus:ring-offset-2",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mailbird-blue-light)] focus-visible:ring-offset-2",
                "transition-all duration-200"
              )}
              onClick={() => handleQuestionClick(question)}
              disabled={isProcessing || sessionQuestionCount >= 5}
              aria-label={`Ask follow-up question: ${question}`}
              aria-describedby={sessionQuestionCount >= 5 ? 'questions-limit-reached' : undefined}
            >
              <MessageCircle className="h-3 w-3 mr-2 flex-shrink-0" aria-hidden="true" />
              <span className="line-clamp-2">{question}</span>
              <ChevronRight className="h-3 w-3 ml-auto flex-shrink-0 opacity-50" aria-hidden="true" />
            </Button>
          ))}
        </div>
        
        {sessionQuestionCount >= 3 && sessionQuestionCount < 5 && (
          <p className="text-xs text-muted-foreground text-center">
            You have {remainingQuestions} follow-up {remainingQuestions === 1 ? 'question' : 'questions'} left in this session
          </p>
        )}
        
        {sessionQuestionCount >= 5 && (
          <p id="questions-limit-reached" className="text-xs text-amber-600 dark:text-amber-400 text-center" role="alert">
            You've used all 5 follow-up questions for this session
          </p>
        )}
      </div>
    </Card>
  )
}