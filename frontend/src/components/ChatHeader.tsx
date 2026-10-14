import { Menu, Wifi, WifiOff } from "lucide-react";
import type { Dataset } from "../types";
import { DatasetSelector } from "./DatasetSelector";

interface ChatHeaderProps {
  title: string;
  datasets: Dataset[];
  selectedDataset: Dataset | undefined;
  isOnline: boolean;
  healthChecked: boolean;
  onOpenSidebar: () => void;
  onSelectDataset: (dataset: Dataset) => void;
}

export function ChatHeader({
  title,
  datasets,
  selectedDataset,
  isOnline,
  healthChecked,
  onOpenSidebar,
  onSelectDataset,
}: ChatHeaderProps) {
  const statusText = !healthChecked
    ? "Đang kiểm tra API"
    : isOnline
      ? "API sẵn sàng"
      : "Chưa kết nối API";

  return (
    <header className="chat-header">
      <button
        aria-label="Mở thanh điều hướng"
        className="icon-button mobile-menu-button"
        onClick={onOpenSidebar}
        type="button"
      >
        <Menu size={20} />
      </button>
      <div className="chat-title">
        <strong>{title}</strong>
        <DatasetSelector datasets={datasets} onSelect={onSelectDataset} selectedDataset={selectedDataset} />
      </div>
      <div
        className={`health-status ${isOnline ? "health-status--online" : ""}`}
        role="status"
        aria-label={statusText}
      >
        {isOnline ? <Wifi size={14} /> : <WifiOff size={14} />}
        <span>{statusText}</span>
      </div>
    </header>
  );
}
