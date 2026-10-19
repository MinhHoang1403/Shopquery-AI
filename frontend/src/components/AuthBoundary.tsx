import { useEffect, useState, type ReactNode } from "react";
import { ChatApiError, getCurrentSession, logoutSession, resetSessionRequests, setSessionCsrf,
  type SessionInfo } from "../api";

export function AuthBoundary({ children }: {
  children: (session: SessionInfo, logout: () => void) => ReactNode;
}) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let controller = new AbortController();
    let active = true;
    const expired = () => {
      resetSessionRequests();
      setSession(null);
      setError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    };
    window.addEventListener("shopquery:session-expired", expired);
    const checkSession = () => {
      controller.abort();
      resetSessionRequests();
      controller = new AbortController();
      const current = controller;
      setSession(null);
      setLoading(true);
      getCurrentSession(current.signal).then((result) => {
        if (!active || current !== controller) return;
        setSessionCsrf(result.csrf_token);
        setSession(result);
        setError(null);
      }).catch((reason: unknown) => {
        if (!active || current !== controller || (reason instanceof DOMException && reason.name === "AbortError")) return;
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
  }, []);

  function logout() {
    const pending = logoutSession();
    setSession(null);
    setError(null);
    pending.catch(() => setError("Không thể xác nhận đăng xuất phía máy chủ. Vui lòng thử lại khi có kết nối."));
  }

  if (loading) return <main className="auth-screen" role="status">Đang kiểm tra phiên đăng nhập…</main>;
  if (session) return children(session, logout);
  return <main className="auth-screen"><section className="auth-card">
    <div className="auth-symbol" aria-hidden="true">SQ</div>
    <h1>ShopQuery AI</h1>
    <p>Phân tích dữ liệu thông minh<br />với SQL, RAG và AI.</p>
    {error ? <p role="alert">{error}</p> : null}
    <a className="google-login" href="/api/auth/login">Tiếp tục với Google</a>
    <small>Chỉ dành cho tài khoản được mời tham gia beta.</small>
    <small>Knowledge và Gemini có thể nhận dữ liệu câu hỏi, kết quả truy vấn hoặc tài liệu để xử lý. Không tải dữ liệu chưa được phép chia sẻ với các nhà cung cấp này.</small>
  </section></main>;
}
