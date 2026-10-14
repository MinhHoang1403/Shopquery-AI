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

export interface ConversationEntry {
  id: number;
  role: "user" | "assistant" | "error";
  text: string;
  response?: ChatResponse;
}
