import { ChatApiError, parseChatResponse } from "./api";
import type { ConversationDetail, ConversationMessage, ConversationSendResponse, ConversationSummary, Dataset, ModelId, ModelsResponse, RelationshipClient, RelationshipPreview, RelationshipRecord } from "./types";

export interface GuestFileInfo {
  file_id: string; filename: string; kind: "table" | "document"; size: number;
  row_count: number | null; columns: Dataset["columns"]; chunk_count: number;
}

export interface GuestStatus extends ModelsResponse {
  remaining: number; ai_enabled: boolean; ttl_seconds: number;
  max_files: number; max_file_bytes: number; max_rows: number; max_columns: number;
  max_pages?: number; max_session_bytes?: number; max_chunks?: number;
  files: GuestFileInfo[]; limited?: boolean; expired?: boolean;
  sql_join_v1_enabled?: boolean;
}

interface GuestSession extends GuestStatus { token: string; csrf_token: string }
export interface GuestPreview extends GuestFileInfo {
  rows: Record<string, unknown>[]; sheet_names: string[]; sheet_name: string | null; warnings: string[];
}

export function guestDataset(status: GuestStatus): Dataset | undefined {
  if (status.files.length === 0) return undefined;
  const tables = status.files.filter((file) => file.kind === "table");
  return {
    dataset_id: 1, kind: "uploaded", name: "Tệp tạm · phiên khách", created_at: null,
    original_filename: tables[0]?.filename ?? null, file_type: null, sheet_name: null,
    row_count: tables[0]?.row_count ?? null, column_count: tables[0]?.columns.length ?? null,
    columns: tables[0]?.columns ?? [], table_count: tables.length,
    document_count: status.files.length - tables.length,
  };
}

export function createGuestClient(onStatus: (value: GuestStatus) => void) {
  let session: Promise<GuestSession> | null = null;
  let current: GuestSession | null = null;
  let closed = false;
  let nextMessage = 0;
  const requests = new Set<AbortController>();
  const conversations = new Map<string, ConversationDetail>();

  function ensureOpen() {
    if (closed) throw new DOMException("Guest page changed", "AbortError");
  }

  function update(status: GuestStatus) {
    ensureOpen();
    const { token, csrf_token, ...safe } = status as GuestSession;
    void token; void csrf_token;
    onStatus(safe);
    if (current) current = { ...current, ...status };
  }

  async function read(response: Response) {
    ensureOpen();
    if (response.status === 413) throw new ChatApiError("Tệp hoặc yêu cầu vượt giới hạn dung lượng phiên khách.", "validation", 413);
    const body = response.status === 204 ? null : await response.json();
    ensureOpen();
    if (!response.ok) {
      const remaining = response.headers.get("X-Guest-Remaining");
      if (current && remaining !== null && /^\d+$/.test(remaining)) update({ ...current, remaining: Number(remaining) });
      if (current && ((response.status === 429 && response.headers.get("X-Guest-Limit") === "chat") || response.status === 410)) {
        update({ ...current, limited: response.status === 429, expired: response.status === 410 });
      }
      const retry = Number(response.headers.get("Retry-After"));
      const hint = response.status === 429 && retry > 0 ? ` Thử lại sau khoảng ${Math.ceil(retry / 60)} phút.` : "";
      throw new ChatApiError((typeof body?.detail === "string" ? body.detail : "Không thể xử lý yêu cầu khách.") + hint, "server", response.status);
    }
    return body;
  }

  async function initialize(): Promise<GuestSession> {
    ensureOpen();
    if (!session) session = (async () => {
      const controller = new AbortController(); requests.add(controller);
      try {
        const body = await read(await fetch("/api/guest/session", {
          method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
          body: "{}", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
        }));
        if (typeof body?.token !== "string" || typeof body?.csrf_token !== "string" ||
            typeof body.remaining !== "number" || typeof body.ai_enabled !== "boolean" ||
            !Array.isArray(body.files) || !Array.isArray(body.models)) {
          throw new ChatApiError("Phiên khách không hợp lệ.", "invalid_response");
        }
        current = body as GuestSession;
        const { token, csrf_token, ...status } = current;
        void token; void csrf_token;
        update(status);
        return current;
      } finally { requests.delete(controller); }
    })();
    return session;
  }

  async function request(path: string, options: RequestInit = {}) {
    const auth = await initialize();
    ensureOpen();
    const controller = new AbortController(); requests.add(controller);
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(240_000), ...(options.signal ? [options.signal] : [])]);
    try {
      const headers = new Headers(options.headers);
      headers.set("X-Guest-Token", auth.token); headers.set("X-Guest-CSRF", auth.csrf_token);
      return await read(await fetch(`/api/guest/${path}`, { ...options, credentials: "same-origin", headers, signal }));
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
      if (reason instanceof ChatApiError) throw reason;
      throw new ChatApiError("Không thể kết nối phiên khách. Vui lòng thử lại.", "network");
    } finally { requests.delete(controller); }
  }

  function detail(id: string) {
    ensureOpen();
    const value = conversations.get(id);
    if (!value) throw new ChatApiError("Không tìm thấy đoạn chat tạm.", "validation", 404);
    return value;
  }

  async function fileRequest(file: File, sheet: string | null | undefined, preview: boolean, signal?: AbortSignal) {
    const limits = await initialize();
    if (file.size > limits.max_file_bytes) throw new ChatApiError("Tệp vượt giới hạn dung lượng phiên khách.", "validation", 413);
    const options = new URLSearchParams({ filename: file.name });
    if (sheet) options.set("sheet_name", sheet);
    const body = await request(`files${preview ? "/preview" : ""}?${options}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file, signal,
    });
    update(body.status);
    return body as { preview: GuestPreview; status: GuestStatus };
  }

  return {
    async getDatasets() { const value = guestDataset(await initialize()); return value ? [value] : []; },
    relationships: {
      list: async (signal) => await request("relationships", { signal }),
      preview: async (input) => await request("relationships/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }) as RelationshipPreview,
      confirm: async (input) => await request("relationships", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }) as RelationshipRecord,
      remove: async (id) => { await request(`relationships/${encodeURIComponent(id)}?confirmed=true`, { method: "DELETE" }); },
    } satisfies RelationshipClient,
    async getModels() { return await initialize(); },
    async getConversations() { ensureOpen(); return [...conversations.values()]; },
    async getConversation(id: string) { return detail(id); },
    async createConversation(datasetId: number | null, modelId?: ModelId): Promise<ConversationSummary> {
      const status = await initialize();
      ensureOpen();
      const now = new Date().toISOString();
      const value: ConversationDetail = {
        conversation_id: crypto.randomUUID(), title: "Đoạn chat tạm thời", dataset_id: datasetId,
        dataset_name: "Tệp tạm", model_id: modelId ?? status.default_model,
        created_at: now, updated_at: now, messages: [],
      };
      conversations.set(value.conversation_id, value);
      return value;
    },
    async renameConversation(id: string, title: string) { const value = detail(id); value.title = title; return value; },
    async deleteConversation(id: string) { ensureOpen(); conversations.delete(id); },
    async setConversationModel(id: string, model: ModelId) { const value = detail(id); value.model_id = model; return value; },
    async sendConversationMessage(id: string, message: string, signal?: AbortSignal, modelId?: ModelId): Promise<ConversationSendResponse> {
      const conversation = detail(id);
      const body = await request("chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, model_id: modelId ?? conversation.model_id }), signal,
      });
      ensureOpen();
      const response = parseChatResponse(body.response);
      update(body.status);
      const now = new Date().toISOString();
      const user: ConversationMessage = { message_id: ++nextMessage, role: "user", content: message, response: null, created_at: now };
      const assistant: ConversationMessage = { message_id: ++nextMessage, role: response.error ? "error" : "assistant", content: response.answer, response, created_at: now };
      conversation.messages.push(user, assistant);
      conversation.title = conversation.title === "Đoạn chat tạm thời" ? message.slice(0, 60) : conversation.title;
      conversation.updated_at = now;
      return { conversation, user_message: user, assistant_message: assistant };
    },
    previewFile: (file: File, sheet?: string | null, signal?: AbortSignal) => fileRequest(file, sheet, true, signal),
    importFile: (file: File, sheet?: string | null) => fileRequest(file, sheet, false),
    dispose() {
      if (closed) return;
      closed = true;
      for (const controller of requests) controller.abort();
      requests.clear(); conversations.clear();
      if (current) {
        void fetch("/api/guest/reset", {
          method: "POST", credentials: "same-origin", keepalive: true,
          headers: { "Content-Type": "application/json", "X-Guest-Token": current.token, "X-Guest-CSRF": current.csrf_token }, body: "{}",
        }).catch(() => undefined);
      }
      current = null;
    },
  };
}

export type GuestClient = ReturnType<typeof createGuestClient>;
