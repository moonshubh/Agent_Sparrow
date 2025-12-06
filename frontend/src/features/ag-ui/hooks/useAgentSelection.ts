import { useCallback, useEffect, useState } from 'react'
import { agentsAPI, type AgentMeta } from '@/services/api/endpoints/agents'
import { safeGetItem, safeSetItem } from '../utils'

export type AgentChoice = 'auto' | 'primary' | 'log_analysis' | 'research'

const STORAGE_KEY = 'agent:selected'

export function useAgentSelection() {
  const [agents, setAgents] = useState<AgentMeta[]>([])
  const [selected, setSelected] = useState<AgentChoice>(() => {
    const saved = safeGetItem(STORAGE_KEY) as AgentChoice | null
    if (saved === 'auto' || saved === 'primary' || saved === 'log_analysis' || saved === 'research') return saved
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
    safeSetItem(STORAGE_KEY, value)
  }, [])

  return { agents, selected, choose }
}
