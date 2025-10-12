"use client"

import React, { PropsWithChildren, useCallback, useState } from 'react'

type Props = PropsWithChildren<{
  onFiles: (files: File[]) => void | Promise<void>
  accept?: string
  className?: string
}>

export function FileDropZone({ onFiles, accept, className, children }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files || [])
    if (files.length) onFiles(files)
  }, [onFiles])

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      aria-label="Drop files to attach"
      className={[
        'relative',
        dragOver ? 'ring-2 ring-primary/70 ring-offset-2 ring-offset-background rounded-xl' : '',
        className || ''
      ].join(' ')}
    >
      {children}
      {dragOver && (
        <div className="absolute inset-0 rounded-xl bg-muted/40 pointer-events-none" />
      )}
      {/* Hidden accept hint for a11y */}
      <input aria-hidden tabIndex={-1} className="hidden" accept={accept} />
    </div>
  )
}

