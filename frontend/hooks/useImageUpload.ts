import { useCallback, useEffect } from 'react'
import { Editor } from '@tiptap/react'
import { uploadImageToSupabase } from '@/lib/storage'

interface UseImageUploadOptions {
  editor: Editor | null
  conversationId: number
  enabled?: boolean
}

export function useImageUpload({ editor, conversationId, enabled = true }: UseImageUploadOptions) {
  const handleImageFile = useCallback(async (file: File): Promise<void> => {
    if (!file.type.startsWith('image/')) return
    if (!editor) return

    try {
      const url = await uploadImageToSupabase(file, conversationId)
      editor.chain().focus().setImage({ src: url }).run()
    } catch (error) {
      console.error('Image upload failed:', error)
    }
  }, [editor, conversationId])

  useEffect(() => {
    if (!editor || !enabled) return

    const view = editor.view
    if (!view?.dom) return

    const handlePaste = async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return

      for (const item of Array.from(items)) {
        if (item.kind === 'file') {
          const file = item.getAsFile()
          if (file && file.type.startsWith('image/')) {
            e.preventDefault()
            try {
              await handleImageFile(file)
            } catch (error) {
              console.error('Failed to handle pasted image:', error)
            }
            break
          }
        }
      }
    }

    const handleDrop = async (e: DragEvent) => {
      const files = e.dataTransfer?.files
      if (!files) return

      const imageFile = Array.from(files).find(f => f.type.startsWith('image/'))
      if (imageFile) {
        e.preventDefault()
        try {
          await handleImageFile(imageFile)
        } catch (error) {
          console.error('Failed to handle dropped image:', error)
        }
      }
    }

    view.dom.addEventListener('paste', handlePaste)
    view.dom.addEventListener('drop', handleDrop)

    return () => {
      view.dom?.removeEventListener('paste', handlePaste)
      view.dom?.removeEventListener('drop', handleDrop)
    }
  }, [editor, enabled, handleImageFile])

  return { handleImageFile }
}