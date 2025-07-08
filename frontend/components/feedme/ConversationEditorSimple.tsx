/**
 * ConversationEditor - Simplified Version
 * Basic conversation editing modal
 */

'use client'

import React, { useState, useEffect, useCallback } from 'react'
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

    try {
      setLoading(true)
      const conversation = await feedMeApi.getConversation(conversationId)
      setTitle(conversation.title || '')
      setContent(conversation.metadata?.content || conversation.raw_transcript || '')
    } catch (error) {
      console.error('Failed to load conversation:', error)
      uiActions.showToast({
        type: 'error',
        title: 'Load Failed',
        message: error instanceof Error && error.message.includes('not found') 
          ? 'Conversation not found. It may have been deleted or moved.'
          : 'Failed to load conversation details.'
      })
      // Close the editor if conversation doesn't exist
      if (error instanceof Error && error.message.includes('not found')) {
        onClose()
      }
    } finally {
      setLoading(false)
    }
  }, [conversationId, uiActions, onClose])

  useEffect(() => {
    if (isOpen && conversationId && conversationId > 0) {
      loadConversation()
    }
  }, [conversationId, isOpen, loadConversation])

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