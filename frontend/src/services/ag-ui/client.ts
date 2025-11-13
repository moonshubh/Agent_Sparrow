import { HttpAgent } from '@ag-ui/client';
import type { RunAgentInput, Message } from '@ag-ui/core';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface AgentConfig {
  sessionId: string;
  traceId: string;
  provider?: string;
  model?: string;
  agentType?: string;
  useServerMemory?: boolean;
  attachments?: any[];
}

export function createSparrowAgent(config: AgentConfig) {
  const agent = new HttpAgent({
    url: `${API_URL}/api/v1/copilot/stream`,
    headers: {
      'Authorization': `Bearer ${getAuthToken()}`,
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    threadId: config.sessionId,
  });

  // Set initial properties for forwardedProps
  agent.state = {
    session_id: config.sessionId,
    trace_id: config.traceId,
    provider: config.provider || 'google',
    model: config.model || 'gemini-2.5-flash',
    agent_type: config.agentType,
    use_server_memory: config.useServerMemory ?? true,
    attachments: config.attachments || [],
  };

  return agent;
}

// Helper to get auth token from localStorage or cookies
function getAuthToken(): string {
  // Check localStorage first
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('authToken');
    if (token) return token;

    // Check session storage
    const sessionToken = sessionStorage.getItem('authToken');
    if (sessionToken) return sessionToken;
  }

  // Return empty string if no token found (anonymous access)
  return '';
}

// Export types for use in components
export type { Message, RunAgentInput } from '@ag-ui/core';