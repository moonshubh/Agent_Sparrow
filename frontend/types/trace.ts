export type StepStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export type TimelineStep = {
  id: string;
  title: string;
  status: StepStatus;
  details?: {
    text?: string;
    toolIO?: unknown;
  };
  ts?: number;
};

export type TimelineInput = {
  dataParts?: Array<{ type: string; data?: any }>;
  metadata?: any;
  content?: string;
  agentType?: 'primary' | 'log_analysis' | 'research' | 'router';
  isStreaming?: boolean;
};
