import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthBoundary } from "./components/AuthBoundary";
import "./styles.css";

const containerDevelopment = import.meta.env.DEV && window.location.port === "8080";
if (containerDevelopment) document.title = "ShopQuery AI — Development";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {containerDevelopment && <div className="development-notice">
      Development · Database thử nghiệm riêng · AI trả phí đang tắt
    </div>}
    <AuthBoundary guest={<App key="guest-page" accessMode="guest" />}>{(session, logout) =>
      <App key={session.user.user_id} account={session.user} onLogout={logout} />
    }</AuthBoundary>
  </StrictMode>,
);
