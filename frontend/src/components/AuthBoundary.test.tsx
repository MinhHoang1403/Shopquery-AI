import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthBoundary } from "./AuthBoundary";
import { getDatasets, resetSessionRequests, setSessionCsrf, createDataset, pauseSessionRequests } from "../api";

const session = (name: string) => ({
  user: { user_id: name, display_name: name, email: `${name}@example.invalid` }, csrf_token: `csrf-${name}`,
});
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

afterEach(() => { cleanup(); resetSessionRequests(); vi.unstubAllGlobals(); });

function boundary() {
  return render(<AuthBoundary>{(value, logout) => <div>
    <p>Private workspace {value.user.display_name}</p>
    <button onClick={logout}>Đăng xuất</button>
  </div>}</AuthBoundary>);
}

it("checks the session before showing private UI and does not load global data for guests", async () => {
  const fetch = vi.fn(async (url: RequestInfo | URL) => { void url; return json({ detail: "Login required" }, 401); });
  vi.stubGlobal("fetch", fetch);
  boundary();
  expect(screen.getByRole("status")).toHaveTextContent("Đang kiểm tra");
  expect(await screen.findByRole("link", { name: "Tiếp tục với Google" })).toHaveAttribute("href", "/api/auth/login");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/auth/me");
});

it("shows an authenticated account, clears private UI immediately on logout and sends CSRF", async () => {
  const fetch = vi.fn(async (url: RequestInfo | URL) => url === "/api/auth/me"
    ? json(session("A")) : new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  boundary();
  await screen.findByText("Private workspace A");
  fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
  expect(screen.queryByText("Private workspace A")).not.toBeInTheDocument();
  await screen.findByRole("link", { name: "Tiếp tục với Google" });
  expect(fetch).toHaveBeenCalledWith("/api/auth/logout", expect.objectContaining({
    method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": "csrf-A" },
  }));
});

it("unmounts account A and loads B after focus session validation", async () => {
  let account = "A";
  vi.stubGlobal("fetch", vi.fn(async () => json(session(account))));
  boundary();
  await screen.findByText("Private workspace A");
  account = "B";
  fireEvent(window, new Event("focus"));
  expect(screen.getByText("Private workspace A")).not.toBeVisible();
  await screen.findByText("Private workspace B");
  expect(screen.queryByText("Private workspace A")).not.toBeInTheDocument();
});

it("discards late private responses from a previous session even if fetch ignores abort", async () => {
  let finish: (value: Response) => void = () => undefined;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
  const request = getDatasets();
  const rejected = expect(request).rejects.toMatchObject({ name: "AbortError" });
  resetSessionRequests();
  setSessionCsrf("csrf-B");
  finish(json([{ name: "private A" }]));
  await rejected;
});

it("preserves the selected file and draft after validating the same session on focus", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json(session("A"))));
  render(<AuthBoundary>{() => <><input aria-label="Private draft" /><input aria-label="Selected file" type="file" /></>}</AuthBoundary>);
  const input = await screen.findByLabelText("Private draft");
  const picker = screen.getByLabelText("Selected file") as HTMLInputElement;
  const file = new File(["Name,Fee\nA,100"], "fees.csv");
  fireEvent.change(input, { target: { value: "Keep draft" } });
  fireEvent.change(picker, { target: { files: [file] } });
  fireEvent(window, new Event("focus"));
  await waitFor(() => expect(screen.getByLabelText("Private draft")).toBeVisible());
  expect(screen.getByLabelText("Private draft")).toHaveValue("Keep draft");
  expect((screen.getByLabelText("Selected file") as HTMLInputElement).files?.[0]).toBe(file);
});

it("queues writes during validation and drops them if identity changes", async () => {
  const fetch = vi.fn(async () => json({ dataset_id: 1 }));
  vi.stubGlobal("fetch", fetch);
  const resume = pauseSessionRequests();
  const write = createDataset("Unsent private workspace");
  const rejected = expect(write).rejects.toMatchObject({ name: "AbortError" });
  await Promise.resolve();
  expect(fetch).not.toHaveBeenCalled();
  resetSessionRequests();
  resume();
  await rejected;
  expect(fetch).not.toHaveBeenCalled();
});

it("does not cancel an already authorized upload when focus confirms the same session", async () => {
  let finish: (response: Response) => void = () => undefined;
  vi.stubGlobal("fetch", vi.fn((url: RequestInfo | URL) => url === "/api/auth/me"
    ? Promise.resolve(json(session("A")))
    : new Promise<Response>((resolve) => { finish = resolve; })));
  boundary();
  await screen.findByText("Private workspace A");
  const upload = createDataset("In-flight authorized upload");
  const result = upload.then((value) => ({ value, error: null }), (error: unknown) => ({ value: null, error }));
  fireEvent(window, new Event("focus"));
  await waitFor(() => expect(screen.getByText("Private workspace A")).toBeVisible());
  finish(json({ dataset_id: 99 }));
  expect(await result).toEqual({ value: { dataset_id: 99 }, error: null });
});

it("resumes queued writes with revalidated CSRF for the same session", async () => {
  const fetch = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => { void url; void options; return json({ dataset_id: 1 }); });
  vi.stubGlobal("fetch", fetch);
  const resume = pauseSessionRequests();
  const write = createDataset("Kept workspace");
  expect(fetch).not.toHaveBeenCalled();
  setSessionCsrf("revalidated-csrf");
  resume();
  await write;
  expect(new Headers(fetch.mock.calls[0][1]?.headers).get("X-CSRF-Token")).toBe("revalidated-csrf");
});

it("holds in-flight private responses until focus verification, then rejects a changed session", async () => {
  let finish: (value: Response) => void = () => undefined;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
  const request = getDatasets();
  let settled = false;
  const outcome = request.then(() => { settled = true; return "unsafe"; }, (error: unknown) => { settled = true; return (error as Error).name; });
  await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
  const resume = pauseSessionRequests();
  finish(json([{ name: "private A" }]));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(settled).toBe(false);
  resetSessionRequests();
  resume();
  expect(await outcome).toBe("AbortError");
});

it("fails closed and removes private state when focus verification fails", async () => {
  let fail = false;
  vi.stubGlobal("fetch", vi.fn(async () => {
    if (fail) throw new TypeError("Offline");
    return json(session("A"));
  }));
  boundary();
  await screen.findByText("Private workspace A");
  fail = true;
  fireEvent(window, new Event("focus"));
  expect(screen.getByText("Private workspace A")).not.toBeVisible();
  await screen.findByRole("link", { name: "Tiếp tục với Google" });
  expect(screen.queryByText("Private workspace A")).not.toBeInTheDocument();
});

it("clears private UI when a private API returns 401", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => url === "/api/auth/me"
    ? json(session("A")) : json({ detail: "Expired" }, 401)));
  boundary();
  await screen.findByText("Private workspace A");
  await act(async () => { await expect(getDatasets()).rejects.toMatchObject({ status: 401 }); });
  await screen.findByRole("link", { name: "Tiếp tục với Google" });
  expect(screen.queryByText("Private workspace A")).not.toBeInTheDocument();
});

it("attaches session-bound CSRF headers and same-origin credentials to writes", async () => {
  const fetch = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => { void url; void options; return json({ dataset_id: 1 }); });
  vi.stubGlobal("fetch", fetch);
  setSessionCsrf("session-bound-token");
  await createDataset("Sales");
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  const options = fetch.mock.calls[0][1] as RequestInit;
  expect(options.credentials).toBe("same-origin");
  expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("session-bound-token");
});

it("does not claim logout succeeded on network failure and retries with revalidated CSRF", async () => {
  let failures = 1;
  let signedIn = true;
  const fetch = vi.fn(async (url: RequestInfo | URL) => {
    if (url === "/api/auth/me") return signedIn ? json(session("A")) : json({}, 401);
    if (failures-- > 0) throw new TypeError("Offline");
    signedIn = false;
    return new Response(null, { status: 204 });
  });
  vi.stubGlobal("fetch", fetch);
  boundary();
  await screen.findByText("Private workspace A");
  fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
  const retry = await screen.findByRole("button", { name: "Thử đăng xuất lại" });
  expect(screen.getByRole("alert")).toHaveTextContent("Chưa xác nhận");
  fireEvent(window, new Event("focus"));
  expect(screen.queryByText("Private workspace A")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Tiếp tục với Google" })).not.toBeInTheDocument();
  fireEvent.click(retry);
  await screen.findByRole("link", { name: "Tiếp tục với Google" });
  expect(fetch).toHaveBeenLastCalledWith("/api/auth/logout", expect.objectContaining({
    headers: { "X-CSRF-Token": "csrf-A" },
  }));
});

it("keeps private UI unmounted while logout is in progress", async () => {
  let finish: (response: Response) => void = () => undefined;
  vi.stubGlobal("fetch", vi.fn((url) => url === "/api/auth/me"
    ? Promise.resolve(json(session("A")))
    : new Promise<Response>((resolve) => { finish = resolve; })));
  boundary();
  await screen.findByText("Private workspace A");
  fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
  expect(screen.getByRole("status")).toHaveTextContent("Đang đăng xuất");
  fireEvent(window, new Event("focus"));
  expect(screen.queryByText("Private workspace A")).not.toBeInTheDocument();
  await act(async () => finish(new Response(null, { status: 204 })));
  await screen.findByRole("link", { name: "Tiếp tục với Google" });
});

it("renders the guest chat instead of a login wall, preserving page state on focus", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({}, 401)));
  render(<AuthBoundary guest={<input aria-label="Guest draft" />}>{() => <p>Private</p>}</AuthBoundary>);
  const input = await screen.findByLabelText("Guest draft");
  fireEvent.change(input, { target: { value: "Not lost on focus" } });
  fireEvent(window, new Event("focus"));
  await waitFor(() => expect(screen.getByLabelText("Guest draft")).toHaveValue("Not lost on focus"));
  expect(screen.queryByText("Private")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Tiếp tục với Google" })).not.toBeInTheDocument();
});

it("returns to fresh guest content only after logout was acknowledged", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => url === "/api/auth/me" ? json(session("A")) : new Response(null, { status: 204 })));
  render(<AuthBoundary guest={<p>Fresh guest chat</p>}>{(value, logout) => <><p>Private {value.user.display_name}</p><button onClick={logout}>Logout</button></>}</AuthBoundary>);
  await screen.findByText("Private A");
  fireEvent.click(screen.getByRole("button", { name: "Logout" }));
  await screen.findByText("Fresh guest chat");
  expect(screen.queryByText("Private A")).not.toBeInTheDocument();
});
