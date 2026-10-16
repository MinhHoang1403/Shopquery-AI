import type {
  ChatResponse,
  ConversationDetail,
  ConversationSendResponse,
  ConversationSummary,
  Dataset,
  DatasetDocument,
  DatasetPreview,
  HealthResponse,
  RouteLabel,
  SourceReference,
} from "./types";

const ROUTES = new Set<RouteLabel>(["SQL", "RAG", "HYBRID", "UNSUPPORTED"]);

export class ChatApiError extends Error {
  constructor(
    message: string,
    public readonly kind: "network" | "validation" | "server" | "business" | "invalid_response",
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ChatApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function isSource(value: unknown): value is SourceReference {
  return (
    isRecord(value) &&
    typeof value.chunk_id === "number" &&
    typeof value.source_file === "string" &&
    typeof value.section_title === "string" &&
    typeof value.content === "string"
  );
}

function parseChatResponse(value: unknown): ChatResponse {
  if (
    !isRecord(value) ||
    typeof value.answer !== "string" ||
    !(value.route === null || (typeof value.route === "string" && ROUTES.has(value.route as RouteLabel))) ||
    !isNullableString(value.sql) ||
    !Array.isArray(value.rows) ||
    !value.rows.every(isRecord) ||
    !Array.isArray(value.sources) ||
    !value.sources.every(isSource) ||
    !isNullableString(value.error)
  ) {
    throw new ChatApiError("Phản hồi từ máy chủ không đúng định dạng.", "invalid_response");
  }
  return value as unknown as ChatResponse;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new ChatApiError("Máy chủ trả về nội dung không hợp lệ.", "invalid_response", response.status);
  }
}

async function requestJson(
  url: string,
  options: RequestInit = {},
  validationMessage = "Dữ liệu gửi lên không hợp lệ.",
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ChatApiError(
      "Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.",
      "network",
    );
  }
  if (response.status === 204) return null;
  const body = await readJson(response);
  if (!response.ok) {
    const detail = isRecord(body) && typeof body.detail === "string" ? body.detail : null;
    if (response.status === 409) {
      throw new ChatApiError(detail ?? "Dữ liệu đã tồn tại.", "validation", response.status);
    }
    if (response.status === 404) {
      throw new ChatApiError(detail ?? "Không tìm thấy dữ liệu.", "validation", response.status);
    }
    if (response.status === 422) {
      throw new ChatApiError(detail ?? validationMessage, "validation", response.status);
    }
    throw new ChatApiError("Máy chủ gặp sự cố. Vui lòng thử lại sau.", "server", response.status);
  }
  return body;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const body = await requestJson("/api/health", { signal });
  if (!isRecord(body) || typeof body.status !== "string" || typeof body.service !== "string") {
    throw new ChatApiError("Health response không hợp lệ.", "invalid_response");
  }
  return body as unknown as HealthResponse;
}

export async function sendChat(message: string, datasetId?: number | null): Promise<ChatResponse> {
  const body = await requestJson("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, dataset_id: datasetId ?? null }),
  });
  const parsed = parseChatResponse(body);
  if (parsed.error !== null) {
    throw new ChatApiError(parsed.answer, "business", 200);
  }
  return parsed;
}

export async function getConversations(signal?: AbortSignal): Promise<ConversationSummary[]> {
  const body = await requestJson("/api/conversations?limit=100", { signal });
  if (!Array.isArray(body)) throw new ChatApiError("Danh sách chat không hợp lệ.", "invalid_response");
  return body as ConversationSummary[];
}

export async function createConversation(datasetId: number | null): Promise<ConversationSummary> {
  return await requestJson("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId }),
  }) as ConversationSummary;
}

export async function getConversation(
  conversationId: string,
  signal?: AbortSignal,
): Promise<ConversationDetail> {
  return await requestJson(`/api/conversations/${conversationId}`, { signal }) as ConversationDetail;
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<ConversationSummary> {
  return await requestJson(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }) as ConversationSummary;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await requestJson(`/api/conversations/${conversationId}`, { method: "DELETE" });
}

export async function sendConversationMessage(
  conversationId: string,
  message: string,
  signal?: AbortSignal,
): Promise<ConversationSendResponse> {
  const body = await requestJson(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!isRecord(body) || !isRecord(body.user_message) || !isRecord(body.assistant_message)) {
    throw new ChatApiError("Phản hồi hội thoại không hợp lệ.", "invalid_response");
  }
  const result = body as unknown as ConversationSendResponse;
  if (result.assistant_message.response) parseChatResponse(result.assistant_message.response);
  return result;
}

export async function getDatasets(signal?: AbortSignal): Promise<Dataset[]> {
  const body = await requestJson("/api/datasets", { signal });
  if (!Array.isArray(body)) throw new ChatApiError("Danh sách dữ liệu không hợp lệ.", "invalid_response");
  return body as Dataset[];
}

export async function createDataset(name: string): Promise<Dataset> {
  return await requestJson("/api/datasets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }) as Dataset;
}

export async function previewDataset(
  file: File,
  sheetName?: string | null,
  signal?: AbortSignal,
  datasetId?: number | null,
): Promise<DatasetPreview> {
  const form = new FormData();
  form.append("file", file);
  if (sheetName) form.append("sheet_name", sheetName);
  const url = datasetId
    ? `/api/datasets/${datasetId}/tables/preview`
    : "/api/datasets/preview";
  return await requestJson(url, {
    method: "POST",
    body: form,
    signal,
  }, "File không hợp lệ.") as DatasetPreview;
}

export async function importDataset(
  file: File,
  datasetName: string,
  sheetName?: string | null,
): Promise<Dataset> {
  const form = new FormData();
  form.append("file", file);
  form.append("dataset_name", datasetName);
  if (sheetName) form.append("sheet_name", sheetName);
  return await requestJson("/api/datasets/import", {
    method: "POST",
    body: form,
  }, "Không thể import file.") as Dataset;
}

export async function importDatasetTable(
  datasetId: number,
  file: File,
  displayName: string,
  sheetName?: string | null,
): Promise<Dataset> {
  const form = new FormData();
  form.append("file", file);
  form.append("display_name", displayName);
  if (sheetName) form.append("sheet_name", sheetName);
  return await requestJson(`/api/datasets/${datasetId}/tables/import`, {
    method: "POST",
    body: form,
  }, "Không thể import bảng.") as Dataset;
}

export async function getDatasetDocuments(datasetId: number): Promise<DatasetDocument[]> {
  return await requestJson(`/api/datasets/${datasetId}/documents`) as DatasetDocument[];
}

export async function uploadDatasetDocument(
  datasetId: number,
  file: File,
): Promise<DatasetDocument> {
  const form = new FormData();
  form.append("file", file);
  return await requestJson(`/api/datasets/${datasetId}/documents`, {
    method: "POST",
    body: form,
  }, "Không thể nạp tài liệu.") as DatasetDocument;
}

export async function deleteDatasetDocument(
  datasetId: number,
  documentId: number,
): Promise<void> {
  await requestJson(`/api/datasets/${datasetId}/documents/${documentId}`, {
    method: "DELETE",
  });
}
