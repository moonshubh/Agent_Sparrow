// Local type definitions for CopilotKit v1.50 compatibility
export interface BinaryInputContent {
  type: "binary";
  mimeType: string;
  filename: string;
  data: string;
}

export interface TextInputContent {
  type: "text";
  text: string;
}

export interface AttachmentInput {
  name: string;
  mime_type: string;
  data_url: string;
  size: number;
}

export interface DocumentPointer {
  documentId: string;
  title: string;
  content?: string;
  description?: string;
  source: string;
  categories?: string[];
}

export function createBinaryContent(file: File): Promise<BinaryInputContent> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      // Extract base64 data from data URL
      const base64Data = dataUrl.split(",")[1];

      resolve({
        type: "binary",
        mimeType: file.type,
        filename: file.name,
        data: base64Data,
      } as BinaryInputContent);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function createTextContent(text: string): TextInputContent {
  return {
    type: "text",
    text,
  } as TextInputContent;
}

export interface InterruptPayload {
  prompt?: string;
  type?: string;
  options?: Array<{
    value: string;
    label: string;
  }>;
  [key: string]: any;
}

export interface AgentState {
  session_id: string;
  trace_id: string;
  provider: string;
  model: string;
  agent_type?: string;
  use_server_memory: boolean;
  attachments?: AttachmentInput[];
  available_documents?: DocumentPointer[];
  [key: string]: any;
}
