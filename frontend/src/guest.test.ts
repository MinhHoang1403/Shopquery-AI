import { afterEach, expect, it, vi } from "vitest";
import { createGuestClient } from "./guest";

const state = { token: "temporary-page-token", csrf_token: "temporary-csrf", remaining: 5, ai_enabled: true,
  files: [], max_files: 2, max_file_bytes: 2097152, max_rows: 1000, max_columns: 20, ttl_seconds: 600,
  default_model: "inetcloud-knowledge", models: [], gemini_fallback_enabled: false };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => vi.unstubAllGlobals());

it("keeps guest history in memory, uses only public guest endpoints and starts empty on a new page", async () => {
  const fetch = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => { void options; return url === "/api/guest/session" ? json(state) : json({
    response: { answer: "SQL là ngôn ngữ truy vấn.", route: null, sql: null, rows: [], sources: [], error: null }, status: { ...state, remaining: 4 },
  }); });
  vi.stubGlobal("fetch", fetch);
  const client = createGuestClient(vi.fn());
  const conversation = await client.createConversation(null);
  await client.sendConversationMessage(conversation.conversation_id, "SQL là gì?");
  expect((await client.getConversation(conversation.conversation_id)).messages).toHaveLength(2);
  expect(await createGuestClient(vi.fn()).getConversations()).toEqual([]);
  const call = fetch.mock.calls.find(([url]) => url === "/api/guest/chat");
  expect(call).toBeDefined();
  expect(fetch.mock.calls.every(([url]) => String(url).startsWith("/api/guest/"))).toBe(true);
  const options = fetch.mock.calls.find(([url]) => url === "/api/guest/chat")?.[1] as RequestInit;
  expect(JSON.parse(options.body as string)).not.toHaveProperty("dataset_id");
  expect(new Headers(options.headers).get("X-Guest-Token")).toBe(state.token);
});

it("does not restore a late guest response after release even when fetch ignores abort", async () => {
  let finish: (response: Response) => void = () => undefined;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
  const client = createGuestClient(vi.fn());
  const request = client.getModels();
  const rejected = expect(request).rejects.toMatchObject({ name: "AbortError" });
  client.dispose();
  finish(json(state));
  await rejected;
});

it("retains displayed messages and exposes backend quota denial without claiming a fabricated answer", async () => {
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn(async (url) => url === "/api/guest/session" ? json(state) : ++calls === 1 ? json({
    response: { answer: "Explanation", route: null, sql: null, rows: [], sources: [], error: null }, status: { ...state, remaining: 4 },
  }) : new Response(JSON.stringify({ detail: "Quota exhausted" }), { status: 429, headers: { "X-Guest-Limit": "chat" } })));
  const status = vi.fn();
  const client = createGuestClient(status);
  const conversation = await client.createConversation(null);
  await client.sendConversationMessage(conversation.conversation_id, "Question");
  await expect(client.sendConversationMessage(conversation.conversation_id, "More")).rejects.toMatchObject({ status: 429 });
  expect((await client.getConversation(conversation.conversation_id)).messages).toHaveLength(2);
  expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ limited: true }));
});

it("reports an HTML proxy 413 clearly and never exposes guest tokens in React status", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => url === "/api/guest/session" ? json(state) : new Response("<html>too large</html>", { status: 413 })));
  const status = vi.fn();
  const client = createGuestClient(status);
  const conversation = await client.createConversation(null);
  await expect(client.sendConversationMessage(conversation.conversation_id, "Question")).rejects.toMatchObject({ status: 413 });
  for (const [value] of status.mock.calls) {
    expect(value).not.toHaveProperty("token");
    expect(value).not.toHaveProperty("csrf_token");
  }
});

it("reports upload rate Retry-After without locking the chat quota", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => url === "/api/guest/session" ? json(state) : new Response(JSON.stringify({ detail: "Hết lượt xem trước" }), {
    status: 429, headers: { "X-Guest-Limit": "preview", "Retry-After": "120" },
  })));
  const status = vi.fn();
  const client = createGuestClient(status);
  await expect(client.previewFile(new File(["A\n1"], "x.csv"))).rejects.toThrow("2 phút");
  expect(status).not.toHaveBeenCalledWith(expect.objectContaining({ limited: true }));
});

it("updates consumed quota on a failed provider call without creating messages", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => url === "/api/guest/session" ? json(state) : new Response(JSON.stringify({ detail: "Unavailable" }), {
    status: 502, headers: { "X-Guest-Remaining": "4" },
  })));
  const status = vi.fn();
  const client = createGuestClient(status);
  const conversation = await client.createConversation(null);
  await expect(client.sendConversationMessage(conversation.conversation_id, "Question")).rejects.toMatchObject({ status: 502 });
  expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ remaining: 4 }));
  expect((await client.getConversation(conversation.conversation_id)).messages).toEqual([]);
});
