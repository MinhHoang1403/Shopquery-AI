import {
  ChevronLeft,
  ChevronRight,
  Database,
  FileSpreadsheet,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ConversationSummary, Dataset } from "../types";

interface SidebarProps {
  open: boolean;
  collapsed: boolean;
  datasets: Dataset[];
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  selectedDatasetId: number | null;
  onClose: () => void;
  onToggleCollapse: () => void;
  onNewChat: () => void;
  onSelectDataset: (dataset: Dataset) => void;
  onSelectConversation: (conversation: ConversationSummary) => void;
  onRename: (conversation: ConversationSummary) => void;
  onDelete: (conversation: ConversationSummary) => void;
  onUpload: () => void;
}

export function Sidebar({
  open,
  collapsed,
  datasets,
  conversations,
  activeConversationId,
  selectedDatasetId,
  onClose,
  onToggleCollapse,
  onNewChat,
  onSelectDataset,
  onSelectConversation,
  onRename,
  onDelete,
  onUpload,
}: SidebarProps) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  useEffect(() => {
    function closeMenu(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenMenu(null);
    }
    window.addEventListener("keydown", closeMenu);
    return () => window.removeEventListener("keydown", closeMenu);
  }, []);

  return (
    <>
      <div
        aria-hidden="true"
        className={`sidebar-overlay ${open ? "sidebar-overlay--visible" : ""}`}
        onClick={onClose}
      />
      <aside className={`sidebar ${open ? "sidebar--open" : ""} ${collapsed ? "sidebar--collapsed" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-symbol" aria-hidden="true"><Database size={19} /></div>
          <div className="brand-text"><strong>ShopQuery AI</strong><span>Data assistant</span></div>
          <button aria-label="Đóng thanh điều hướng" className="icon-button sidebar-close" onClick={onClose} type="button">
            <X size={19} />
          </button>
        </div>

        <button className="new-chat-button" onClick={onNewChat} type="button">
          <Plus size={18} /><span>Đoạn chat mới</span>
        </button>

        <div className="sidebar-scroll">
          <section className="sidebar-section" aria-labelledby="datasets-heading">
            <div className="sidebar-section-heading">
              <span id="datasets-heading">Dữ liệu</span>
              {!collapsed ? <small>{datasets.length}</small> : null}
            </div>
            <div className="sidebar-list">
              {datasets.map((dataset) => (
                <button
                  aria-current={dataset.dataset_id === selectedDatasetId ? "true" : undefined}
                  className={`sidebar-item ${dataset.dataset_id === selectedDatasetId ? "sidebar-item--active" : ""}`}
                  key={dataset.dataset_id ?? "default"}
                  onClick={() => onSelectDataset(dataset)}
                  title={dataset.name}
                  type="button"
                >
                  {dataset.kind === "default" ? <Database size={16} /> : <FileSpreadsheet size={16} />}
                  <span><strong>{dataset.name}</strong>{dataset.row_count !== null ? <small>{dataset.row_count.toLocaleString("vi-VN")} dòng</small> : null}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="sidebar-section conversation-section" aria-labelledby="conversations-heading">
            <div className="sidebar-section-heading">
              <span id="conversations-heading">Các cuộc trò chuyện</span>
            </div>
            <div className="sidebar-list conversation-list">
              {conversations.length === 0 ? <p className="sidebar-empty">Chưa có cuộc trò chuyện.</p> : null}
              {conversations.map((conversation) => (
                <div className={`conversation-item ${conversation.conversation_id === activeConversationId ? "conversation-item--active" : ""}`} key={conversation.conversation_id}>
                  <button
                    className="conversation-select"
                    onClick={() => onSelectConversation(conversation)}
                    title={conversation.title}
                    type="button"
                  >
                    <span>{conversation.title}</span>
                    <small>{conversation.dataset_name}</small>
                  </button>
                  <button
                    aria-expanded={openMenu === conversation.conversation_id}
                    aria-label={`Tùy chọn cho ${conversation.title}`}
                    className="conversation-menu-button"
                    onClick={() => setOpenMenu((current) => current === conversation.conversation_id ? null : conversation.conversation_id)}
                    type="button"
                  >
                    <MoreHorizontal size={17} />
                  </button>
                  {openMenu === conversation.conversation_id ? (
                    <div className="conversation-menu" role="menu">
                      <button onClick={() => { setOpenMenu(null); onRename(conversation); }} role="menuitem" type="button"><Pencil size={15} /> Đổi tên</button>
                      <button className="danger-action" onClick={() => { setOpenMenu(null); onDelete(conversation); }} role="menuitem" type="button"><Trash2 size={15} /> Xóa</button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="sidebar-footer">
          <button className="upload-button" onClick={onUpload} type="button"><Upload size={17} /><span>Nạp dữ liệu mới</span></button>
          <button aria-label={collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar"} className="collapse-button" onClick={onToggleCollapse} type="button">
            {collapsed ? <ChevronRight size={17} /> : <><PanelLeftClose size={17} /><span>Thu gọn</span><ChevronLeft size={15} /></>}
          </button>
        </div>
      </aside>
    </>
  );
}
