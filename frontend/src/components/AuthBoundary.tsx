import { Database, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChatApiError, getCurrentSession, logoutSession, resetSessionRequests, setSessionCsrf,
  type SessionInfo } from "../api";

type AuthenticatedRenderer = (session: SessionInfo, logout: () => void) => ReactNode;

function AuthenticatedView({ render, session, onLogout }: {
  render: AuthenticatedRenderer;
  session: SessionInfo;
  onLogout: () => void;
}) {
  return render(session, onLogout);
}

export function AuthBoundary({ children, guest }: {
  children: AuthenticatedRenderer;
  guest?: ReactNode;
}) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const logoutState = useRef<"idle" | "pending" | "failed">("idle");
  const wasAuthenticated = useRef(false);

  useEffect(() => {
    let controller = new AbortController();
    let active = true;
    const expired = () => {
      resetSessionRequests();
      setSession(null);
      wasAuthenticated.current = false;
      setLoading(false);
      setError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    };
    window.addEventListener("shopquery:session-expired", expired);
    const checkSession = () => {
      if (logoutState.current !== "idle") return;
      controller.abort();
      if (wasAuthenticated.current) resetSessionRequests();
      controller = new AbortController();
      const current = controller;
      if (wasAuthenticated.current) { setSession(null); setLoading(true); }
      getCurrentSession(current.signal).then((result) => {
        if (!active || current !== controller) return;
        setSessionCsrf(result.csrf_token);
        wasAuthenticated.current = true;
        setSession(result);
        setError(null);
      }).catch((reason: unknown) => {
        if (!active || current !== controller || (reason instanceof DOMException && reason.name === "AbortError")) return;
        wasAuthenticated.current = false;
        if (!(reason instanceof ChatApiError && reason.status === 401)) {
          setError(reason instanceof Error ? reason.message : "Không thể kiểm tra phiên đăng nhập.");
        }
      }).finally(() => { if (active && current === controller) setLoading(false); });
    };
    checkSession();
    window.addEventListener("focus", checkSession);
    return () => {
      active = false;
      controller.abort();
      resetSessionRequests();
      window.removeEventListener("shopquery:session-expired", expired);
      window.removeEventListener("focus", checkSession);
    };
  }, [attempt]);

  async function logout(refreshSession = false) {
    if (logoutState.current === "pending") return;
    logoutState.current = "pending";
    setLogoutPending(true);
    setLogoutFailed(false);
    setSession(null);
    wasAuthenticated.current = false;
    setError(null);
    try {
      if (refreshSession) {
        const current = await getCurrentSession();
        setSessionCsrf(current.csrf_token);
      }
      await logoutSession();
      logoutState.current = "idle";
    } catch (reason) {
      if (reason instanceof ChatApiError && reason.status === 401) {
        resetSessionRequests();
        logoutState.current = "idle";
      } else {
        logoutState.current = "failed";
        setLogoutFailed(true);
        setError("Chưa xác nhận được đăng xuất phía máy chủ. Hãy kết nối mạng và thử đăng xuất lại.");
      }
    } finally {
      setLogoutPending(false);
    }
  }

  if (loading) return <main className="auth-screen"><div className="auth-loading" role="status">
    <LoaderCircle aria-hidden="true" size={22} />Đang kiểm tra phiên đăng nhập…
  </div></main>;
  if (session) return <AuthenticatedView render={children} session={session} onLogout={() => { void logout(); }} />;
  if (guest && !logoutPending && !logoutFailed) return <>{error ? <p className="auth-notice" role="alert">{error}</p> : null}{guest}</>;
  return <main className="auth-screen"><section className="auth-card">
    <div className="auth-symbol" aria-hidden="true"><Database size={24} /></div>
    <h1>ShopQuery AI</h1>
    <h2>Hỏi dữ liệu theo cách tự nhiên.</h2>
    <p>Phân tích dữ liệu, truy vấn SQL<br />và tìm kiếm tài liệu bằng AI.</p>
    {error ? <p className="auth-error" role="alert">{error}</p> : null}
    {logoutPending ? <p role="status">Đang đăng xuất…</p> : logoutFailed ? (
      <button className="google-login" type="button" onClick={() => { void logout(true); }}>Thử đăng xuất lại</button>
    ) : <>
      <a className="google-login" href="/api/auth/login" aria-disabled={signingIn} onClick={(event) => {
        if (signingIn) event.preventDefault();
        else setSigningIn(true);
      }}>{signingIn ? "Đang chuyển đến Google…" : "Tiếp tục với Google"}</a>
      {error ? <button className="auth-retry" type="button" onClick={() => setAttempt((value) => value + 1)}>Kiểm tra phiên lại</button> : null}
    </>}
    <small>Đăng nhập để truy cập không gian dữ liệu của bạn.</small>
    <small>Chỉ dành cho tài khoản được mời tham gia beta.</small>
    <small>Knowledge và Gemini có thể nhận dữ liệu câu hỏi, kết quả truy vấn hoặc tài liệu để xử lý. Không tải dữ liệu chưa được phép chia sẻ với các nhà cung cấp này.</small>
  </section></main>;
}
