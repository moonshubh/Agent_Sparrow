/**
 * ConversationExamples - Q&A Pairs Display and Editing
 * 
 * Displays extracted Q&A pairs from a conversation with confidence scores,
 * search/filter capabilities, and inline editing functionality.
 */

'use client'

import React, { useEffect, useState } from 'react'
import { Search, Plus, RotateCcw, AlertCircle, CheckCircle2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { useConversationsActions, useExamplesByConversation, useExamplesLoading, useExamplesError, type FeedMeExample } from '@/lib/stores/conversations-store'
import { useUIActions } from '@/lib/stores/ui-store'
import { ExampleEditor } from './ExampleEditor'

interface ConversationExamplesProps {
  conversationId: number
}

export function ConversationExamples({ conversationId }: ConversationExamplesProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  
  const examples = useExamplesByConversation(conversationId) || []
  const isLoading = useExamplesLoading(conversationId)
  const error = useExamplesError(conversationId)
  const { loadExamples, refreshExamples, deleteExample } = useConversationsActions()
  const uiActions = useUIActions()

  // Load examples when component mounts
  useEffect(() => {
    if (conversationId > 0) {
      loadExamples(conversationId).catch(console.error)
    }
  }, [conversationId, loadExamples])

  // Filter examples based on search and tag
  const filteredExamples = examples.filter(example => {
    const matchesSearch = !searchQuery || 
      example.question_text.toLowerCase().includes(searchQuery.toLowerCase()) ||
      example.answer_text.toLowerCase().includes(searchQuery.toLowerCase())
    
    const matchesTag = !selectedTag || example.tags.includes(selectedTag)
    
    return matchesSearch && matchesTag
  })

  // Get all unique tags from examples
  const allTags = Array.from(
    new Set(examples.flatMap(example => example.tags))
  ).sort()

  const handleRefresh = async () => {
    try {
      await refreshExamples(conversationId)
    } catch (error) {
      console.error('Failed to refresh examples:', error)
    }
  }

  const handleDeleteExample = async (exampleId: number) => {
    try {
      await deleteExample(exampleId)
      // The success notification and optimistic update are handled by the store action
    } catch (error) {
      console.error('Failed to delete example:', error)
      // Error notification is also handled by the store action
      // This catch block is mainly for any additional error handling if needed
    }
  }

  if (isLoading && examples.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
        <p className="text-sm text-muted-foreground">Loading Q&A examples...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <div className="text-center">
          <p className="text-sm font-medium text-destructive">Failed to load examples</p>
          <p className="text-xs text-muted-foreground">{error}</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh}>
          <RotateCcw className="h-4 w-4 mr-2" />
          Try Again
        </Button>
      </div>
    )
  }

  if (examples.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="rounded-full bg-muted p-4">
          <Plus className="h-6 w-6 text-muted-foreground" />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium">No Q&A examples found</p>
          <p className="text-xs text-muted-foreground">
            This conversation may not contain extractable Q&A examples, or processing hasn't completed yet.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
          <RotateCcw className="h-4 w-4 mr-2" />
          {isLoading ? 'Processing...' : 'Refresh & Reprocess'}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header with search and controls */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold">Q&A Examples</h3>
          <Badge variant="secondary" className="text-xs">
            {examples.length} total
          </Badge>
          {filteredExamples.length !== examples.length && (
            <Badge variant="outline" className="text-xs">
              {filteredExamples.length} filtered
            </Badge>
          )}
        </div>
        
        <div className="flex gap-2">
          <Button 
            variant="outline" 
            size="sm" 
            onClick={handleRefresh}
            disabled={isLoading}
          >
            <RotateCcw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Search and Filter Controls */}
      <div className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search questions and answers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        
        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant={selectedTag === null ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedTag(null)}
              className="h-7 text-xs"
            >
              All Tags
            </Button>
            {allTags.map(tag => (
              <Button
                key={tag}
                variant={selectedTag === tag ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedTag(selectedTag === tag ? null : tag)}
                className="h-7 text-xs"
              >
                {tag}
              </Button>
            ))}
          </div>
        )}
      </div>

      {/* Examples Grid */}
      {filteredExamples.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-sm text-muted-foreground">
            No examples match your current search and filters.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 max-h-none overflow-y-visible">
          {filteredExamples.map(example => (
            <ExampleEditor 
              key={example.id} 
              example={example}
              onDelete={handleDeleteExample}
            />
          ))}
        </div>
      )}
    </div>
  )
}

