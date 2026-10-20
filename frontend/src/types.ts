export type RouteLabel = "SQL" | "RAG" | "HYBRID" | "UNSUPPORTED";
export type ModelId = "inetcloud-knowledge" | "gemini";

// NUMERIC and browser-unsafe integers are exact strings; never coerce cells to Number().
export type ResultRow = Record<string, unknown>;

export interface RelationshipInput {
  source_table_id: string; source_column: string; target_table_id: string; target_column: string;
}
export interface RelationshipPreview extends RelationshipInput {
  revision: string; valid: boolean; cardinality: "many-to-one" | "one-to-one" | null;
  source_rows: number; target_rows: number; source_nulls: number; target_nulls: number;
  target_duplicates: number; orphan_rows: number | null; reasons: string[];
}
export interface RelationshipRecord extends RelationshipPreview { relationship_id: string; confirmed: true }
export interface RelationshipClient {
  list: (signal?: AbortSignal) => Promise<{ enabled: boolean; relationships: RelationshipRecord[] }>;
  preview: (input: RelationshipInput) => Promise<RelationshipPreview>;
  confirm: (input: RelationshipInput & { revision: string; confirmed: true }) => Promise<RelationshipRecord>;
  remove: (id: string) => Promise<void>;
}

export interface ModelOption {
  id: ModelId;
  label: string;
  provider: string;
  configured: boolean;
}

export interface ModelsResponse {
  ai_enabled?: boolean;
  default_model: ModelId;
  models: ModelOption[];
  gemini_fallback_enabled: boolean;
}

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
  rows: ResultRow[];
  sources: SourceReference[];
  error: string | null;
  requested_model?: ModelId | null;
  used_model?: ModelId | null;
  fallback_used?: boolean;
  fallback_reason?: string | null;
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

export interface DatasetTable {
  dataset_table_id: number | null;
  display_name: string;
  original_filename: string | null;
  file_type: string | null;
  sheet_name: string | null;
  row_count: number;
  column_count: number;
  columns: DatasetColumn[];
}

export interface DatasetDocument {
  document_id: number;
  dataset_id: number;
  original_filename: string;
  file_type: string;
  title: string;
  chunk_count: number;
  created_at: string;
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
  table_count?: number;
  document_count?: number;
  tables?: DatasetTable[];
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
  rows: ResultRow[];
  warnings: string[];
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  dataset_id: number | null;
  dataset_name: string;
  created_at: string;
  updated_at: string;
  model_id?: ModelId;
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
