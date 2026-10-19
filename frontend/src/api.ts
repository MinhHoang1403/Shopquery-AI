import type {
  ChatResponse,
  ConversationDetail,
  ConversationSendResponse,
  ConversationSummary,
  Dataset,
  DatasetDocument,
  DatasetPreview,
  HealthResponse,
  ModelId,
  ModelsResponse,
  RouteLabel,
  RelationshipClient,
  RelationshipPreview,
  RelationshipRecord,
  SourceReference,
} from "./types";

const ROUTES = new Set<RouteLabel>(["SQL", "RAG", "HYBRID", "UNSUPPORTED"]);
let sessionEpoch = 0;
let csrfToken: string | null = null;
const pendingRequests = new Set<AbortController>();
let sessionCheck: Promise<void> | null = null;

export function pauseSessionRequests(): () => void {
  let resolve: () => void = () => undefined;
  const check = new Promise<void>((done) => { resolve = done; });
  sessionCheck = check;
  return () => {
    if (sessionCheck === check) sessionCheck = null;
    resolve();
  };
}

export function resetSessionRequests() {
  sessionEpoch += 1;
  csrfToken = null;
  for (const controller of pendingRequests) controller.abort();
  pendingRequests.clear();
}

export function setSessionCsrf(token: string) {
  csrfToken = token;
}

function assertCurrentEpoch(epoch: number) {
  if (epoch !== sessionEpoch) throw new DOMException("Session changed", "AbortError");
}

async function awaitVerifiedSession(epoch: number) {
  while (sessionCheck) await sessionCheck;
  assertCurrentEpoch(epoch);
}

export interface SessionInfo {
  user: { user_id: string; email: string; display_name: string };
  csrf_token: string;
}

export async function getCurrentSession(signal?: AbortSignal): Promise<SessionInfo> {
  const result = await requestJson("/api/auth/me", { signal });
  if (!isRecord(result) || !isRecord(result.user) || typeof result.user.user_id !== "string" ||
      typeof result.user.email !== "string" || typeof result.user.display_name !== "string" ||
      typeof result.csrf_token !== "string") {
    throw new ChatApiError("Phiên đăng nhập không hợp lệ.", "invalid_response");
  }
  return result as unknown as SessionInfo;
}

export async function logoutSession(): Promise<void> {
  const token = csrfToken;
  resetSessionRequests();
  const result = await fetch("/api/auth/logout", {
    method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": token ?? "" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!result.ok && result.status !== 401) throw new Error("Không thể xác nhận đăng xuất phía máy chủ.");
}

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

export function parseChatResponse(value: unknown): ChatResponse {
  if (
    !isRecord(value) ||
    typeof value.answer !== "string" ||
    !(value.route === null || (typeof value.route === "string" && ROUTES.has(value.route as RouteLabel))) ||
    !isNullableString(value.sql) ||
    !Array.isArray(value.rows) ||
    !value.rows.every(isRecord) ||
    !Array.isArray(value.sources) ||
    !value.sources.every(isSource) ||
    !isNullableString(value.error) ||
    ![undefined, null, "gemini", "inetcloud-knowledge"].includes(value.requested_model as string | null | undefined) ||
    ![undefined, null, "gemini", "inetcloud-knowledge"].includes(value.used_model as string | null | undefined) ||
    !(value.fallback_used === undefined || typeof value.fallback_used === "boolean") ||
    !(value.fallback_reason === undefined || isNullableString(value.fallback_reason))
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
  const epoch = sessionEpoch;
  if (url !== "/api/auth/me" && url !== "/api/health") {
    if (sessionCheck) await awaitVerifiedSession(epoch);
    assertCurrentEpoch(epoch);
    options.signal?.throwIfAborted();
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  pendingRequests.add(controller);
  try {
    const headers = new Headers(options.headers);
    if (csrfToken && !["GET", "HEAD"].includes(options.method ?? "GET")) {
      headers.set("X-CSRF-Token", csrfToken);
    }
    response = await fetch(url, { ...options, credentials: "same-origin", headers,
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(240_000)]) });
    if (url !== "/api/auth/me" && url !== "/api/health") await awaitVerifiedSession(epoch);
    assertCurrentEpoch(epoch);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ChatApiError(
      "Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.",
      "network",
    );
  } finally {
    options.signal?.removeEventListener("abort", abort);
    pendingRequests.delete(controller);
  }
  if (response.status === 401 || response.headers.get("X-Session-Invalid") === "1") {
    if (url !== "/api/auth/me") window.dispatchEvent(new Event("shopquery:session-expired"));
    throw new ChatApiError("Phiên đăng nhập không còn được phép sử dụng.", "server", response.status);
  }
  if (response.status === 204) return null;
  if (response.status === 413) {
    throw new ChatApiError("Tệp vượt giới hạn dung lượng cho phép. Xem hạn mức từ máy chủ trong hộp tải tệp.", "validation", 413);
  }
  const body = await readJson(response);
  if (url !== "/api/auth/me" && url !== "/api/health") await awaitVerifiedSession(epoch);
  assertCurrentEpoch(epoch);
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
    if (response.status === 403 || response.status === 429) {
      const retry = Number(response.headers.get("Retry-After"));
      const hint = response.status === 429 && retry > 0 ? ` Thử lại sau khoảng ${Math.ceil(retry / 60)} phút.` : "";
      throw new ChatApiError((detail ?? "Yêu cầu không được phép hoặc đã vượt giới hạn.") + hint, "validation", response.status);
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

export async function getModels(signal?: AbortSignal): Promise<ModelsResponse> {
  const body = await requestJson("/api/models", { signal });
  if (!isRecord(body) || !Array.isArray(body.models) ||
    !(body.default_model === "gemini" || body.default_model === "inetcloud-knowledge") ||
    !body.models.every((model) => isRecord(model) &&
      (model.id === "gemini" || model.id === "inetcloud-knowledge") &&
      typeof model.label === "string" && typeof model.configured === "boolean")) {
    throw new ChatApiError("Danh sách mô hình không hợp lệ.", "invalid_response");
  }
  return body as unknown as ModelsResponse;
}

export interface UploadLimits {
  max_file_bytes: number; max_rows: number; max_columns: number; max_pdf_pages: number;
  provider_data_enabled: boolean; preview_per_hour: number; upload_per_hour: number;
  sql_join_v1_enabled?: boolean;
}

export async function getUploadLimits(signal?: AbortSignal): Promise<UploadLimits> {
  const body = await requestJson("/api/uploads/limits", { signal });
  if (!isRecord(body) || ![body.max_file_bytes, body.max_rows, body.max_columns, body.max_pdf_pages].every((value) => typeof value === "number" && value > 0) || typeof body.provider_data_enabled !== "boolean") {
    throw new ChatApiError("Không thể đọc giới hạn tải tệp từ máy chủ.", "invalid_response");
  }
  return body as unknown as UploadLimits;
}

export async function setConversationModel(conversationId: string, modelId: ModelId) {
  return await requestJson(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId }),
  }) as ConversationSummary;
}

export async function createConversation(
  datasetId: number | null, modelId?: ModelId,
): Promise<ConversationSummary> {
  return await requestJson("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, model_id: modelId }),
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
  modelId?: ModelId,
): Promise<ConversationSendResponse> {
  const body = await requestJson(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, model_id: modelId }),
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

export async function getDataset(datasetId: number): Promise<Dataset> {
  return await requestJson(`/api/datasets/${datasetId}`) as Dataset;
}

export function createRelationshipClient(datasetId: number): RelationshipClient {
  const path = `/api/datasets/${datasetId}/relationships`;
  return {
    list: async (signal) => await requestJson(path, { signal }) as Awaited<ReturnType<RelationshipClient["list"]>>,
    preview: async (input) => await requestJson(`${path}/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    }) as RelationshipPreview,
    confirm: async (input) => await requestJson(path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    }) as RelationshipRecord,
    remove: async (id) => { await requestJson(`${path}/${encodeURIComponent(id)}?confirmed=true`, { method: "DELETE" }); },
  };
}

export async function deleteDataset(datasetId: number, deleteConversations = false): Promise<void> {
  await requestJson(`/api/datasets/${datasetId}?delete_conversations=${deleteConversations}`, {
    method: "DELETE",
  });
}

export async function deleteDatasetTable(datasetId: number, tableId: number): Promise<void> {
  await requestJson(`/api/datasets/${datasetId}/tables/${tableId}`, { method: "DELETE" });
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
