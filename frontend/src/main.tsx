import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthBoundary } from "./components/AuthBoundary";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthBoundary guest={<App key="guest-page" accessMode="guest" />}>{(session, logout) =>
      <App key={session.user.user_id} account={session.user} onLogout={logout} />
    }</AuthBoundary>
  </StrictMode>,
);
