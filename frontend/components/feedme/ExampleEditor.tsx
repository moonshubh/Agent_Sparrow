/**
 * ExampleEditor - Rich Text Editor for Q&A Examples
 * 
 * A Tiptap-based rich text editor for editing individual Q&A examples
 * with inline editing, optimistic updates, and error handling.
 */

'use client'

import React, { useState, useEffect } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import { 
  Bold, 
  Italic, 
  List, 
  ListOrdered, 
  Quote, 
  Save, 
  X, 
  Edit3,
  Loader2,
  Trash2
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { MarkdownMessage } from '@/components/markdown/MarkdownMessage'
import { useConversationsActions, type FeedMeExample } from '@/lib/stores/conversations-store'
import { autoFormatContent } from '@/lib/content-formatter'

interface ExampleEditorProps {
  example: FeedMeExample
  onCancel?: () => void
  onSave?: (example: FeedMeExample) => void
  onDelete?: (exampleId: number) => void
}

export function ExampleEditor({ example, onCancel, onSave, onDelete }: ExampleEditorProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [tags, setTags] = useState<string[]>(example.tags)
  const [newTag, setNewTag] = useState('')
  
  const { updateExample } = useConversationsActions()

  // Question editor
  const questionEditor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        horizontalRule: false,
      }),
      Placeholder.configure({
        placeholder: 'Enter the customer question or issue...',
      }),
      CharacterCount.configure({
        limit: 1000,
      }),
    ],
    content: example.question_text,
    editable: isEditing,
  })

  // Answer editor
  const answerEditor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        horizontalRule: false,
      }),
      Placeholder.configure({
        placeholder: 'Enter the support response or solution...',
      }),
      CharacterCount.configure({
        limit: 2000,
      }),
    ],
    content: example.answer_text,
    editable: isEditing,
  })

  // Update editor editability when editing state changes
  useEffect(() => {
    questionEditor?.setEditable(isEditing)
    answerEditor?.setEditable(isEditing)
  }, [isEditing, questionEditor, answerEditor])

  const handleEdit = () => {
    setIsEditing(true)
  }

  const handleCancel = () => {
    setIsEditing(false)
    setTags(example.tags)
    setNewTag('')
    questionEditor?.commands.setContent(example.question_text)
    answerEditor?.commands.setContent(example.answer_text)
    onCancel?.()
  }

  const handleSave = async () => {
    if (!questionEditor || !answerEditor) return

    const questionText = questionEditor.getText()
    const answerText = answerEditor.getText()

    if (!questionText.trim() || !answerText.trim()) {
      return
    }

    setIsSaving(true)

    try {
      const updates: Partial<FeedMeExample> = {
        question_text: questionText,
        answer_text: answerText,
        tags: tags,
        updated_at: new Date().toISOString()
      }

      await updateExample(example.id, updates)
      
      setIsEditing(false)
      onSave?.({ ...example, ...updates })
      
    } catch (error) {
      console.error('Failed to save example:', error)
      // Error handling will be managed by the store and displayed elsewhere
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      // For now, we'll call the onDelete prop if provided
      // Later we'll add API integration for individual example deletion
      onDelete?.(example.id)
    } catch (error) {
      console.error('Failed to delete example:', error)
    } finally {
      setIsDeleting(false)
    }
  }

  const addTag = () => {
    const tag = newTag.trim()
    if (tag && !tags.includes(tag)) {
      setTags([...tags, tag])
      setNewTag('')
    }
  }

  const removeTag = (tagToRemove: string) => {
    setTags(tags.filter(tag => tag !== tagToRemove))
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addTag()
    }
  }

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-100 text-green-800 border-green-200'
    if (score >= 0.6) return 'bg-yellow-100 text-yellow-800 border-yellow-200'
    return 'bg-red-100 text-red-800 border-red-200'
  }

  const getConfidenceLabel = (score: number) => {
    if (score >= 0.8) return 'High'
    if (score >= 0.6) return 'Medium'
    return 'Low'
  }

  return (
    <Card className={`${isEditing ? 'ring-2 ring-accent' : 'hover:shadow-sm'} transition-all`}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Question</span>
            {example.confidence_score !== undefined && (
              <Badge 
                variant="outline" 
                className={`text-xs ${getConfidenceColor(example.confidence_score)}`}
              >
                {getConfidenceLabel(example.confidence_score)} ({Math.round(example.confidence_score * 100)}%)
              </Badge>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            {!isEditing ? (
              <>
                <Button variant="ghost" size="sm" onClick={handleEdit}>
                  <Edit3 className="h-4 w-4" />
                </Button>
                {onDelete && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive hover:bg-destructive/10">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Q&A Example</AlertDialogTitle>
                        <AlertDialogDescription>
                          Are you sure you want to delete this Q&A example? This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction 
                          onClick={handleDelete}
                          disabled={isDeleting}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {isDeleting ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                          ) : (
                            <Trash2 className="h-4 w-4 mr-2" />
                          )}
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
              </>
            ) : (
              <>
                <Button variant="ghost" size="sm" onClick={handleCancel} disabled={isSaving}>
                  <X className="h-4 w-4" />
                </Button>
                <Button 
                  variant="default" 
                  size="sm" 
                  onClick={handleSave} 
                  disabled={isSaving}
                >
                  {isSaving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                </Button>
              </>
            )}
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="pt-0 space-y-4">
        {/* Question Editor */}
        <div className={`${isEditing ? 'border border-border rounded-md p-3' : ''}`}>
          {isEditing ? (
            <>
              <EditorToolbar editor={questionEditor} />
              <EditorContent 
                editor={questionEditor} 
                className="prose prose-sm max-w-none min-h-[80px]"
              />
              {questionEditor && (
                <div className="text-xs text-muted-foreground mt-2">
                  {questionEditor.storage.characterCount.characters()}/1000 characters
                </div>
              )}
            </>
          ) : (
            <MarkdownMessage content={autoFormatContent(example.question_text, false)} />
          )}
        </div>

        {/* Answer Editor */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="h-4 w-4 rounded-full bg-accent flex-shrink-0" />
            <span className="text-xs font-medium text-muted-foreground">Answer</span>
          </div>
          
          <div className={`${isEditing ? 'border border-border rounded-md p-3' : ''}`}>
            {isEditing ? (
              <>
                <EditorToolbar editor={answerEditor} />
                <EditorContent 
                  editor={answerEditor} 
                  className="prose prose-sm max-w-none min-h-[120px]"
                />
                {answerEditor && (
                  <div className="text-xs text-muted-foreground mt-2">
                    {answerEditor.storage.characterCount.characters()}/2000 characters
                  </div>
                )}
              </>
            ) : (
              <MarkdownMessage content={autoFormatContent(example.answer_text, true)} />
            )}
          </div>
        </div>

        {/* Tags Editor */}
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {tags.map(tag => (
              <div key={tag} className="flex items-center">
                <Badge variant="secondary" className="text-xs">
                  {tag}
                  {isEditing && (
                    <button
                      onClick={() => removeTag(tag)}
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </Badge>
              </div>
            ))}
            
            {/* Issue and Resolution type badges */}
            {example.issue_type && (
              <Badge variant="outline" className="text-xs">
                Issue: {example.issue_type}
              </Badge>
            )}
            {example.resolution_type && (
              <Badge variant="outline" className="text-xs">
                Resolution: {example.resolution_type}
              </Badge>
            )}
          </div>
          
          {isEditing && (
            <div className="flex gap-2">
              <Input
                placeholder="Add tag..."
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyPress={handleKeyPress}
                className="flex-1 h-8 text-xs"
              />
              <Button variant="outline" size="sm" onClick={addTag}>
                Add
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

interface EditorToolbarProps {
  editor: any
}

function EditorToolbar({ editor }: EditorToolbarProps) {
  if (!editor) return null

  return (
    <div className="flex items-center gap-1 pb-2 mb-2 border-b">
      <Button
        variant={editor.isActive('bold') ? 'default' : 'ghost'}
        size="sm"
        onClick={() => editor.chain().focus().toggleBold().run()}
        className="h-8 w-8 p-0"
      >
        <Bold className="h-4 w-4" />
      </Button>
      
      <Button
        variant={editor.isActive('italic') ? 'default' : 'ghost'}
        size="sm"
        onClick={() => editor.chain().focus().toggleItalic().run()}
        className="h-8 w-8 p-0"
      >
        <Italic className="h-4 w-4" />
      </Button>
      
      <Button
        variant={editor.isActive('bulletList') ? 'default' : 'ghost'}
        size="sm"
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        className="h-8 w-8 p-0"
      >
        <List className="h-4 w-4" />
      </Button>
      
      <Button
        variant={editor.isActive('orderedList') ? 'default' : 'ghost'}
        size="sm"
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        className="h-8 w-8 p-0"
      >
        <ListOrdered className="h-4 w-4" />
      </Button>
      
      <Button
        variant={editor.isActive('blockquote') ? 'default' : 'ghost'}
        size="sm"
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        className="h-8 w-8 p-0"
      >
        <Quote className="h-4 w-4" />
      </Button>
    </div>
  )
}