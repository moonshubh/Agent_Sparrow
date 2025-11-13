import { useEffect, useState } from 'react';
import { useAgent } from './useAgent';
import type { AgentState } from '@/services/ag-ui/types';

export function useAgentState<T = AgentState>(): T | null {
  const { agent } = useAgent();
  const [state, setState] = useState<T | null>(null);

  useEffect(() => {
    if (!agent) return;

    // Initialize with current state FIRST
    setState(agent.state as T);

    // Then subscribe to state changes
    const subscription = agent.subscribe({
      onStateChanged: ({ state: newState }) => {
        setState(newState as T);
      },
    });

    // Cleanup subscription on unmount
    return () => {
      if (subscription && typeof subscription.unsubscribe === 'function') {
        subscription.unsubscribe();
      }
    };
  }, [agent]);

  return state;
}