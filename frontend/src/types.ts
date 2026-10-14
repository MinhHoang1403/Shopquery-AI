export type RouteLabel = "SQL" | "RAG" | "HYBRID" | "UNSUPPORTED";

export interface SourceReference {
  chunk_id: number;
  source_file: string;
  section_title: string;
  content: string;
}

export interface ChatResponse {
  answer: string;
  route: RouteLabel | null;
  sql: string | null;
  rows: Record<string, unknown>[];
  sources: SourceReference[];
  error: string | null;
}

export interface HealthResponse {
  status: string;
  service: string;
}

export interface DatasetColumn {
  source_name: string;
  name: string;
  data_type: string;
}

export interface Dataset {
  dataset_id: number | null;
  kind: "default" | "uploaded";
  name: string;
  original_filename: string | null;
  file_type: string | null;
  sheet_name: string | null;
  row_count: number | null;
  column_count: number | null;
  columns: DatasetColumn[];
  created_at: string | null;
}

export interface DatasetPreview {
  filename: string;
  file_type: string;
  sheet_name: string | null;
  sheet_names: string[];
  row_count: number;
  column_count: number;
  columns: DatasetColumn[];
  rows: Record<string, unknown>[];
  warnings: string[];
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  dataset_id: number | null;
  dataset_name: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  message_id: number;
  role: "user" | "assistant" | "error";
  content: string;
  response: ChatResponse | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface ConversationSendResponse {
  conversation: ConversationSummary;
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
}

export interface ConversationEntry {
  id: string;
  role: "user" | "assistant" | "error";
  text: string;
  response?: ChatResponse;
}
