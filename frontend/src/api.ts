import type { ChatResponse, HealthResponse, RouteLabel, SourceReference } from "./types";

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
    throw new ChatApiError(
      "Phản hồi từ máy chủ không đúng định dạng.",
      "invalid_response",
    );
  }

  return value as unknown as ChatResponse;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new ChatApiError(
      "Máy chủ trả về nội dung không hợp lệ.",
      "invalid_response",
      response.status,
    );
  }
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { signal });
  if (!response.ok) {
    throw new Error("Health check failed");
  }

  const body: unknown = await response.json();
  if (!isRecord(body) || typeof body.status !== "string" || typeof body.service !== "string") {
    throw new Error("Invalid health response");
  }

  return body as unknown as HealthResponse;
}

export async function sendChat(message: string): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  } catch {
    throw new ChatApiError(
      "Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.",
      "network",
    );
  }

  const body = await readJson(response);
  if (!response.ok) {
    if (response.status === 422) {
      throw new ChatApiError(
        "Câu hỏi không hợp lệ. Vui lòng kiểm tra nội dung và độ dài.",
        "validation",
        response.status,
      );
    }

    throw new ChatApiError(
      "Máy chủ gặp sự cố khi xử lý câu hỏi. Vui lòng thử lại sau.",
      "server",
      response.status,
    );
  }

  const parsed = parseChatResponse(body);
  if (parsed.error !== null) {
    throw new ChatApiError(
      parsed.answer || "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
      "business",
      response.status,
    );
  }

  return parsed;
}
