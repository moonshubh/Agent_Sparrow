import { apiClient } from "@/services/api/api-client";

export type AgentId = "primary" | "log_analysis" | "research";

export interface AgentMeta {
  id: AgentId;
  destination: "primary_agent" | "log_analyst" | "researcher";
  name: string;
  description: string;
  tools?: string[];
  aliases?: string[];
  icon?: string | null;
}

export const agentsAPI = {
  async list(): Promise<AgentMeta[]> {
    try {
      return await apiClient.get<AgentMeta[]>("/api/v1/agents");
    } catch (e) {
      if (process.env.NODE_ENV === "development") {
        console.debug("agentsAPI.list fallback due to error:", e);
      }
      // Safe fallback with minimal metadata
      return [
        {
          id: "primary",
          destination: "primary_agent",
          name: "Primary Support",
          description: "General queries & KB",
        },
        {
          id: "log_analysis",
          destination: "log_analyst",
          name: "Log Analysis",
          description: "Logs, errors, performance",
        },
        {
          id: "research",
          destination: "researcher",
          name: "Research",
          description: "Web research & sources",
        },
      ];
    }
  },

  async get(id: string): Promise<AgentMeta> {
    return apiClient.get<AgentMeta>(`/api/v1/agents/${encodeURIComponent(id)}`);
  },
};
