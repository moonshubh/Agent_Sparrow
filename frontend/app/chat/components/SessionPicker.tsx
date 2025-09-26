"use client"

import React, { useEffect, useMemo, useState } from 'react'
import { sessionsAPI, type ChatSession, type AgentType } from '@/lib/api/sessions'

type Props = {
  value?: string
  onChange: (sessionId: string | undefined) => void
}

export function SessionPicker({ value, onChange }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const selected = useMemo(() => sessions.find(s => s.id === value), [sessions, value])

  useEffect(() => {
    let mounted = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const items = await sessionsAPI.list(50, 0)
        if (!mounted) return
        setSessions(items)
      } catch (e: any) {
        if (!mounted) return
        setError(e?.message || 'Failed to load sessions')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [])

  const create = async () => {
    try {
      const s = await sessionsAPI.create('primary')
      setSessions(prev => [s, ...prev])
      onChange(s.id)
      setRenameValue(s.title || '')
    } catch (e) {
      console.error('Failed to create session', e)
    }
  }

  const rename = async () => {
    if (!value) return
    const title = renameValue.trim()
    if (!title) return
    try {
      const updated = await sessionsAPI.rename(value, title)
      setSessions(prev => prev.map(s => (s.id === value ? updated : s)))
    } catch (e) {
      console.error('Failed to rename session', e)
    }
  }

  const remove = async () => {
    if (!value) return
    try {
      await sessionsAPI.remove(value)
      setSessions(prev => prev.filter(s => s.id !== value))
      onChange(undefined)
      setRenameValue('')
    } catch (e) {
      console.error('Failed to delete session', e)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <label className="flex items-center gap-2">
        <span className="text-muted-foreground">Session</span>
        <select
          className="border rounded p-1 w-56"
          value={value || ''}
          onChange={(e) => {
            const id = e.target.value || undefined
            onChange(id)
            const sel = sessions.find(s => s.id === id)
            setRenameValue(sel?.title || '')
          }}
        >
          <option value="">No session</option>
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {(s.title && s.title.trim()) ? s.title : `Session ${s.id}`}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="px-2 py-1 text-sm border rounded" onClick={create} disabled={loading}>
        {loading ? 'Loading…' : 'New'}
      </button>
      <input
        className="border rounded p-1 text-sm w-40"
        placeholder="Rename"
        value={renameValue}
        onChange={(e) => setRenameValue(e.target.value)}
        disabled={!value}
      />
      <button type="button" className="px-2 py-1 text-sm border rounded" onClick={rename} disabled={!value || !renameValue.trim()}>
        Save
      </button>
      <button type="button" className="px-2 py-1 text-sm border rounded text-red-600" onClick={remove} disabled={!value}>
        Delete
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  )
}

