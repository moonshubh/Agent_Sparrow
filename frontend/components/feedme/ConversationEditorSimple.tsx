/**
 * ConversationEditor - Simplified Version
 * Basic conversation editing modal
 */

'use client'

import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useActions } from '@/lib/stores/feedme-store'
import { feedMeApi } from '@/lib/feedme-api'

interface ConversationEditorProps {
  conversationId: number
  isOpen: boolean
  onClose: () => void
}

export function ConversationEditor({ conversationId, isOpen, onClose }: ConversationEditorProps) {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const actions = useActions()

  useEffect(() => {
    if (isOpen && conversationId && conversationId > 0) {
      loadConversation()
    }
  }, [conversationId, isOpen])

  const loadConversation = async () => {
    try {
      setLoading(true)
      const conversation = await feedMeApi.getConversation(conversationId)
      setTitle(conversation.title || '')
      setContent(conversation.metadata?.content || conversation.raw_transcript || '')
    } catch (error) {
      console.error('Failed to load conversation:', error)
      actions.addNotification({
        type: 'error',
        title: 'Load Failed',
        message: error instanceof Error && error.message.includes('not found') 
          ? 'Conversation not found. It may have been deleted.'
          : 'Failed to load conversation details.'
      })
      // Close the editor if conversation doesn't exist
      if (error instanceof Error && error.message.includes('not found')) {
        onClose()
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    try {
      setLoading(true)
      await actions.editConversation(conversationId, {
        title,
        raw_transcript: content,
        updated_by: 'user'
      })
      onClose()
    } catch (error) {
      console.error('Failed to save conversation:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>Edit Conversation</DialogTitle>
          <DialogDescription>
            Make changes to the conversation title and content
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 overflow-auto">
          <div>
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Conversation title"
            />
          </div>

          <div>
            <Label htmlFor="content">Content</Label>
            <Textarea
              id="content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Conversation content"
              rows={20}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={loading}>
            {loading ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}