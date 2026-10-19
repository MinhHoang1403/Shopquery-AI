import {
  Database,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ConversationSummary } from "../types";
import type { SessionInfo } from "../api";
import { AccountMenu } from "./AccountMenu";

interface SidebarProps {
  account?: SessionInfo["user"];
  onLogout?: () => void;
  guest?: boolean;
  onLogin?: () => void;
  open: boolean;
  collapsed: boolean;
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  onClose: () => void;
  onToggleCollapse: () => void;
  onNewChat: () => void;
  onSelectConversation: (conversation: ConversationSummary) => void;
  onRename: (conversation: ConversationSummary) => void;
  onDelete: (conversation: ConversationSummary) => void;
  onUpload: () => void;
}

export function Sidebar({
  account,
  onLogout,
  guest,
  onLogin,
  open,
  collapsed,
  conversations,
  activeConversationId,
  onClose,
  onToggleCollapse,
  onNewChat,
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
          <button
            aria-label={collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar"}
            className="icon-button desktop-collapse-button"
            onClick={onToggleCollapse}
            title={collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar"}
            type="button"
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button aria-label="Đóng thanh điều hướng" className="icon-button sidebar-close" onClick={onClose} type="button">
            <X size={19} />
          </button>
        </div>

        <button className="new-chat-button" onClick={onNewChat} type="button">
          <Plus size={18} /><span>Đoạn chat mới</span>
        </button>

        <div className="sidebar-scroll">
          <section className="sidebar-section conversation-section" aria-labelledby="conversations-heading">
            <div className="sidebar-section-heading">
              <span id="conversations-heading">{guest ? "Đoạn chat tạm thời" : "Các cuộc trò chuyện"}</span>
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
          <button className="upload-button" onClick={onUpload} type="button" aria-label={guest ? "Tệp tạm thời" : "Quản lý dữ liệu"}><Upload size={17} /><span>{guest ? "Tệp tạm thời" : "Quản lý dữ liệu"}</span></button>
          {guest ? <><button className="guest-sidebar-login" type="button" onClick={onLogin}>Đăng nhập</button><p className="guest-sidebar-hint">Đăng nhập để lưu lịch sử và bộ dữ liệu.</p></> : null}
          {onLogout && account ? <AccountMenu account={account} onLogout={onLogout} /> : null}
        </div>
      </aside>
    </>
  );
}
