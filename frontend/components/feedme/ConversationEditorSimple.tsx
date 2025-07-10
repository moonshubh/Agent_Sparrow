/**
 * ConversationEditor - Simplified Version
 * Basic conversation editing modal
 */

'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { X, ArrowLeft, Save, Loader2, FileText, MessageSquare } from 'lucide-react'
import { useConversationsActions } from '@/lib/stores/conversations-store'
import { useUIActions } from '@/lib/stores/ui-store'
import { feedMeApi } from '@/lib/feedme-api'
import { ConversationExamples } from './ConversationExamples'

interface ConversationEditorProps {
  conversationId: number
  isOpen: boolean
  onClose: () => void
}

export function ConversationEditor({ conversationId, isOpen, onClose }: ConversationEditorProps) {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const uiActions = useUIActions()
  const conversationActions = useConversationsActions()

  // Stable reference to prevent unnecessary re-renders
  const loadConversationRef = useRef<number | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const loadConversation = useCallback(async () => {
    // Validate conversation ID before attempting to load
    if (!conversationId || conversationId <= 0) {
      console.warn('Invalid conversation ID:', conversationId)
      uiActions.showToast({
        type: 'error',
        title: 'Invalid Request',
        message: 'Invalid conversation ID provided.'
      })
      onClose()
      return
    }

    // Prevent multiple simultaneous loads for the same conversation
    if (loadConversationRef.current === conversationId) {
      return
    }

    // Cancel previous request if exists
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Create new abort controller
    const abortController = new AbortController()
    abortControllerRef.current = abortController
    loadConversationRef.current = conversationId

    try {
      setLoading(true)
      
      // Use the store's getConversation method which has proper error handling
      const conversation = await conversationActions.getConversation(conversationId, true)
      
      // Check if request was aborted
      if (abortController.signal.aborted) {
        return
      }
      
      if (!conversation) {
        // Conversation doesn't exist, clean up and close
        console.warn(`Conversation ${conversationId} not found`)
        
        // Remove the stale conversation from the store
        conversationActions.removeConversation(conversationId)
        
        // Show user-friendly message
        uiActions.showToast({
          type: 'warning',
          title: 'Conversation Not Found',
          message: 'This conversation has been deleted or moved.'
        })
        
        // Close the editor immediately
        onClose()
        
        return
      }
      
      // Check if request was aborted before setting state
      if (abortController.signal.aborted) {
        return
      }
      
      // Set the conversation data
      setTitle(conversation.title || '')
      setContent(conversation.metadata?.content || (conversation as any).raw_transcript || '')
      
    } catch (error) {
      // Check if request was aborted
      if (abortController.signal.aborted) {
        return
      }
      
      // Handle different error types
      const isNotFound = error instanceof Error && 
        (error.message.includes('not found') || error.message.includes('404'))
      
      if (isNotFound) {
        console.warn(`Conversation ${conversationId} not found`)
        
        // Remove the stale conversation from the store
        conversationActions.removeConversation(conversationId)
        
        // Show user-friendly message
        uiActions.showToast({
          type: 'warning',
          title: 'Conversation Not Found',
          message: 'This conversation has been deleted or moved.'
        })
        
        // Close the editor immediately
        onClose()
        
        return
      }
      
      // Handle other errors
      console.error('Failed to load conversation:', error)
      
      uiActions.showToast({
        type: 'error',
        title: 'Load Failed',
        message: 'Failed to load conversation details. Please try again.'
      })
      
      // Don't close on non-404 errors, let user retry
      
    } finally {
      if (!abortController.signal.aborted) {
        setLoading(false)
        loadConversationRef.current = null
        abortControllerRef.current = null
      }
    }
  }, [conversationId, uiActions, onClose, conversationActions])

  useEffect(() => {
    if (isOpen && conversationId && conversationId > 0 && !loading && loadConversationRef.current !== conversationId) {
      loadConversation()
    }
  }, [conversationId, isOpen, loading, loadConversation])

  // Cleanup on unmount or conversation change
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      loadConversationRef.current = null
    }
  }, [conversationId])

  // Handle escape key to close
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        onClose()
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      // Prevent body scroll when full-screen modal is open
      document.body.style.overflow = 'hidden'
    }

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  const handleSave = async () => {
    try {
      setLoading(true)
      await conversationActions.editConversation(conversationId, {
        transcript_content: content,
        edit_reason: 'Manual edit via conversation modal',
        user_id: 'demo@mailbird.com'
      })
      // Show success notification
      uiActions.showToast({
        type: 'success',
        title: 'Conversation Saved',
        message: 'The conversation has been successfully updated.'
      })
      
      onClose()
    } catch (error) {
      console.error('Failed to save conversation:', error)
      
      // Show user-friendly error notification
      uiActions.showToast({
        type: 'error',
        title: 'Save Failed',
        message: error instanceof Error && error.message.includes('not found')
          ? 'Conversation not found. It may have been deleted.'
          : 'Failed to save the conversation. Please try again.'
      })
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 bg-background">
      {/* Header */}
      <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={onClose} className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <div>
              <h1 className="text-lg font-semibold">Edit Conversation</h1>
              <p className="text-sm text-muted-foreground">
                View extracted Q&A pairs or edit the raw conversation content
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>
              <X className="h-4 w-4 mr-2" />
              Close
            </Button>
            <Button onClick={handleSave} disabled={loading} variant="default">
              {loading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              {loading ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 h-[calc(100vh-4rem)]">
        <Tabs defaultValue="examples" className="h-full flex flex-col">
          <div className="border-b px-6 py-4">
            <TabsList className="grid grid-cols-2 max-w-md">
              <TabsTrigger value="examples" className="gap-2">
                <MessageSquare className="h-4 w-4" />
                Q&A Examples
              </TabsTrigger>
              <TabsTrigger value="raw" className="gap-2">
                <FileText className="h-4 w-4" />
                Raw Content
              </TabsTrigger>
            </TabsList>
          </div>
          
          <div className="flex-1 overflow-hidden">
            <TabsContent value="examples" className="h-full m-0 p-0">
              <ScrollArea className="h-full">
                <div className="p-6">
                  <ConversationExamples conversationId={conversationId} />
                </div>
              </ScrollArea>
            </TabsContent>
            
            <TabsContent value="raw" className="h-full m-0 p-0">
              <ScrollArea className="h-full">
                <div className="p-6 space-y-6 max-w-4xl">
                  <div className="space-y-2">
                    <Label htmlFor="title" className="text-base font-medium">Title</Label>
                    <Input
                      id="title"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Conversation title"
                      className="text-base"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="content" className="text-base font-medium">Raw Transcript</Label>
                    <Textarea
                      id="content"
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder="Original conversation content"
                      rows={24}
                      className="font-mono text-sm resize-none"
                    />
                  </div>
                </div>
              </ScrollArea>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}
