import { Database, Wifi, WifiOff } from "lucide-react";

interface ChatHeaderProps {
  isOnline: boolean;
  healthChecked: boolean;
}

export function ChatHeader({ isOnline, healthChecked }: ChatHeaderProps) {
  const statusText = !healthChecked
    ? "Đang kiểm tra API"
    : isOnline
      ? "API sẵn sàng"
      : "Chưa kết nối API";

  return (
    <header className="app-header">
      <div className="brand-mark" aria-hidden="true">
        <Database size={22} strokeWidth={2.2} />
      </div>
      <div className="brand-copy">
        <strong>ShopQuery AI</strong>
        <span>Trợ lý dữ liệu cửa hàng</span>
      </div>
      <div
        className={`health-pill ${isOnline ? "health-pill--online" : ""}`}
        role="status"
        aria-label={statusText}
      >
        {isOnline ? <Wifi size={14} /> : <WifiOff size={14} />}
        <span>{statusText}</span>
      </div>
    </header>
  );
}
