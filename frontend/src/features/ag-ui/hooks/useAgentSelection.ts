import { useCallback, useEffect, useState } from 'react'
import { agentsAPI, type AgentMeta } from '@/services/api/endpoints/agents'

export type AgentChoice = 'auto' | 'primary' | 'log_analysis' | 'research'

const STORAGE_KEY = 'agent:selected'

export function useAgentSelection() {
  const [agents, setAgents] = useState<AgentMeta[]>([])
  const [selected, setSelected] = useState<AgentChoice>(() => {
    try {
      if (typeof window !== 'undefined') {
        const saved = window.localStorage.getItem(STORAGE_KEY) as AgentChoice | null
        if (saved === 'auto' || saved === 'primary' || saved === 'log_analysis' || saved === 'research') return saved
      }
    } catch {}
    return 'auto'
  })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const list = await agentsAPI.list()
        if (!cancelled) setAgents(list)
      } catch {
        if (!cancelled) setAgents([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const choose = useCallback((value: AgentChoice) => {
    setSelected(value)
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, value)
      }
    } catch {}
  }, [])

  return { agents, selected, choose }
}
