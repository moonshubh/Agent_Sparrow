import { apiClient } from '@/services/api/api-client'

export type HumanDecisionType = 'accept' | 'ignore' | 'response' | 'edit'

export interface HumanDecisionPayload {
  type: HumanDecisionType
  message?: string
  action?: string
  args?: Record<string, unknown>
}

export interface GraphRunRequest {
  query?: string
  log_content?: string
  thread_id?: string
  resume?: HumanDecisionPayload
}

export interface GraphRunResponse {
  thread_id: string
  status: 'completed' | 'interrupted'
  state?: Record<string, unknown> | null
  interrupts?: Array<Record<string, unknown>> | null
}

export interface GraphStateResponse {
  thread_id: string
  state?: Record<string, unknown> | null
  interrupts?: Array<Record<string, unknown>> | null
}

const RUN_ENDPOINT = '/api/v1/v2/agent/graph/run'

export const agentGraphApi = {
  async run(payload: GraphRunRequest): Promise<GraphRunResponse> {
    return apiClient.post<GraphRunResponse, GraphRunRequest>(RUN_ENDPOINT, payload)
  },
  async getThreadState(threadId: string): Promise<GraphStateResponse> {
    return apiClient.get<GraphStateResponse>(`/api/v1/v2/agent/graph/threads/${encodeURIComponent(threadId)}`)
  },
}
