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
    // Count total follow-up questions used in this session
    let totalUsed = 0
    const sessionUsedQuestions = new Set<string>()
    
    // Go through all messages to count used follow-up questions
    messages.forEach(message => {
      if (message.type === 'user') {
        // Check if this user message was a follow-up question from any previous agent message
        const previousAgentMessages = messages.filter(
          (m, idx) => m.type === 'agent' && 
          idx < messages.indexOf(message) &&
          m.metadata?.followUpQuestions?.includes(message.content)
        )
        
        if (previousAgentMessages.length > 0) {
          sessionUsedQuestions.add(message.content)
          totalUsed++
        }
      }
    })
    
    setUsedQuestions(sessionUsedQuestions)
    setSessionQuestionCount(totalUsed)
    
    // Find the most recent agent message with follow-up questions
    const agentMessages = messages.filter(m => m.type === 'agent').reverse()
    
    for (const message of agentMessages) {
      if (message.metadata?.followUpQuestions && message.metadata.followUpQuestions.length > 0) {
        // Get unused questions from this message
        const questions = message.metadata.followUpQuestions.filter(q => !sessionUsedQuestions.has(q))
        setAvailableQuestions(questions)
        break
      }
    }
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
      "border-accent/20 bg-gradient-to-br from-accent/5 to-transparent p-4",
      className
    )}>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent" />
            <h3 className="text-sm font-medium">Suggested Follow-up Questions</h3>
          </div>
          <span className="text-xs text-muted-foreground">
            {remainingQuestions} remaining
          </span>
        </div>
        
        <div className="grid gap-2">
          {availableQuestions.slice(0, Math.min(3, remainingQuestions)).map((question, index) => (
            <Button
              key={`${question}-${index}`}
              variant="outline"
              size="sm"
              className={cn(
                "justify-start text-left h-auto py-2 px-3 text-sm",
                "hover:bg-accent/10 hover:border-accent/30",
                "transition-all duration-200"
              )}
              onClick={() => handleQuestionClick(question)}
              disabled={isProcessing || sessionQuestionCount >= 5}
            >
              <MessageCircle className="h-3 w-3 mr-2 flex-shrink-0" />
              <span className="line-clamp-2">{question}</span>
              <ChevronRight className="h-3 w-3 ml-auto flex-shrink-0 opacity-50" />
            </Button>
          ))}
        </div>
        
        {sessionQuestionCount >= 3 && sessionQuestionCount < 5 && (
          <p className="text-xs text-muted-foreground text-center">
            You have {remainingQuestions} follow-up {remainingQuestions === 1 ? 'question' : 'questions'} left in this session
          </p>
        )}
        
        {sessionQuestionCount >= 5 && (
          <p className="text-xs text-amber-600 dark:text-amber-400 text-center">
            You've used all 5 follow-up questions for this session
          </p>
        )}
      </div>
    </Card>
  )
}