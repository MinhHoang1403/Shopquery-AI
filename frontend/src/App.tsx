import { Database, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChatApiError,
  createConversation,
  deleteConversation,
  getConversation,
  getConversations,
  getDatasets,
  getHealth,
  renameConversation,
  sendConversationMessage,
} from "./api";
import { ChatHeader } from "./components/ChatHeader";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { ConfirmDialog, RenameDialog } from "./components/Dialogs";
import { DatasetUploadDialog } from "./components/DatasetUploadDialog";
import { Sidebar } from "./components/Sidebar";
import { SuggestedQuestions } from "./components/SuggestedQuestions";
import type {
  ConversationEntry,
  ConversationMessage,
  ConversationSummary,
  Dataset,
} from "./types";

const DEFAULT_QUESTIONS = [
  { label: "Phân tích bán hàng", question: "Top 5 sản phẩm bán chạy nhất tháng 9/2025 là gì?", kind: "analysis" as const },
  { label: "Tra cứu chính sách", question: "Chính sách đổi trả của cửa hàng như thế nào?", kind: "document" as const },
  { label: "Kết hợp dữ liệu", question: "Top 5 sản phẩm bán chạy nhất có thuộc danh mục được miễn phí vận chuyển không?", kind: "hybrid" as const },
];

function errorMessage(error: unknown): string {
  if (error instanceof ChatApiError) return error.message;
  return "Đã xảy ra lỗi không xác định. Vui lòng thử lại.";
}

function entryFromMessage(message: ConversationMessage): ConversationEntry {
  return {
    id: String(message.message_id),
    role: message.role,
    text: message.content,
    response: message.response ?? undefined,
  };
}

function sameDataset(left: number | null, right: number | null) {
  return left === right;
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationEntry[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBooting, setIsBooting] = useState(true);
  const [health, setHealth] = useState({ checked: false, online: false });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<ConversationSummary | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ConversationSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [pendingDataset, setPendingDataset] = useState<Dataset | null>(null);
  const conversationEnd = useRef<HTMLDivElement>(null);
  const requestController = useRef<AbortController | null>(null);
  const activeConversation = useRef<string | null>(null);
  const selectionSequence = useRef(0);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => sameDataset(dataset.dataset_id, selectedDatasetId)) ?? datasets[0],
    [datasets, selectedDatasetId],
  );
  const currentConversation = conversations.find(
    (conversation) => conversation.conversation_id === activeConversationId,
  );
  const datasetName = selectedDataset?.name ?? "Dữ liệu cửa hàng mẫu";
  const suggestions = useMemo(() => {
    if (!selectedDataset || selectedDataset.kind === "default") return DEFAULT_QUESTIONS;
    const firstColumn = selectedDataset.columns[0]?.source_name;
    const secondColumn = selectedDataset.columns[1]?.source_name;
    return [
      { label: "Kiểm tra dữ liệu", question: "Bộ dữ liệu này có tổng cộng bao nhiêu dòng?", kind: "analysis" as const },
      { label: "Phân nhóm", question: firstColumn ? `Hãy đếm số dòng theo cột ${firstColumn}.` : "Hãy phân nhóm dữ liệu theo cột đầu tiên.", kind: "analysis" as const },
      { label: "Tổng hợp", question: secondColumn ? `Hãy tổng hợp các giá trị theo cột ${secondColumn}.` : "Hãy tóm tắt các giá trị số trong dữ liệu.", kind: "analysis" as const },
    ];
  }, [selectedDataset]);

  useEffect(() => {
    const controller = new AbortController();
    const bootstrapSequence = selectionSequence.current;
    getHealth(controller.signal)
      .then((result) => setHealth({ checked: true, online: result.status === "ok" }))
      .catch(() => setHealth({ checked: true, online: false }));

    Promise.all([getDatasets(controller.signal), getConversations(controller.signal)])
      .then(async ([availableDatasets, availableConversations]) => {
        setDatasets(availableDatasets);
        setConversations(availableConversations);
        if (
          availableConversations.length > 0 &&
          selectionSequence.current === bootstrapSequence
        ) {
          const latest = availableConversations[0];
          const detail = await getConversation(latest.conversation_id, controller.signal);
          if (selectionSequence.current !== bootstrapSequence) return;
          activeConversation.current = latest.conversation_id;
          setActiveConversationId(latest.conversation_id);
          setSelectedDatasetId(detail.dataset_id);
          setMessages(detail.messages.map(entryFromMessage));
        }
      })
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setValidationError(errorMessage(error));
        }
      })
      .finally(() => setIsBooting(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, isLoading]);

  function updateDraft(value: string) {
    setDraft(value);
    if (validationError) setValidationError(null);
  }

  function stopPendingRequest() {
    requestController.current?.abort();
    requestController.current = null;
    setIsLoading(false);
  }

  function startNewChat(datasetId = selectedDatasetId) {
    selectionSequence.current += 1;
    stopPendingRequest();
    activeConversation.current = null;
    setActiveConversationId(null);
    setSelectedDatasetId(datasetId);
    setMessages([]);
    setDraft("");
    setValidationError(null);
    setSidebarOpen(false);
  }

  async function selectConversation(conversation: ConversationSummary) {
    if (conversation.conversation_id === activeConversation.current) {
      setSidebarOpen(false);
      return;
    }
    stopPendingRequest();
    const sequence = ++selectionSequence.current;
    setIsBooting(true);
    setValidationError(null);
    try {
      const detail = await getConversation(conversation.conversation_id);
      if (selectionSequence.current !== sequence) return;
      activeConversation.current = detail.conversation_id;
      setActiveConversationId(detail.conversation_id);
      setSelectedDatasetId(detail.dataset_id);
      setMessages(detail.messages.map(entryFromMessage));
      setSidebarOpen(false);
    } catch (error) {
      setValidationError(errorMessage(error));
    } finally {
      if (selectionSequence.current === sequence) setIsBooting(false);
    }
  }

  function upsertConversation(conversation: ConversationSummary) {
    setConversations((current) => [
      conversation,
      ...current.filter((item) => item.conversation_id !== conversation.conversation_id),
    ]);
  }

  async function submitQuestion(questionOverride?: string) {
    if (isLoading || isBooting) return;
    const question = (questionOverride ?? draft).trim();
    if (!question) {
      setValidationError("Vui lòng nhập câu hỏi.");
      return;
    }
    if (question.length > 2_000) {
      setValidationError("Câu hỏi không được vượt quá 2000 ký tự.");
      return;
    }

    setValidationError(null);
    setDraft("");
    let conversationId = activeConversation.current;
    try {
      if (!conversationId) {
        const created = await createConversation(selectedDatasetId);
        conversationId = created.conversation_id;
        activeConversation.current = conversationId;
        setActiveConversationId(conversationId);
        upsertConversation(created);
      }
    } catch (error) {
      setValidationError(errorMessage(error));
      setDraft(question);
      return;
    }

    const requestConversationId = conversationId;
    const optimisticId = `pending-${Date.now()}`;
    setMessages((current) => [...current, { id: optimisticId, role: "user", text: question }]);
    setIsLoading(true);
    const controller = new AbortController();
    requestController.current = controller;

    try {
      const result = await sendConversationMessage(requestConversationId, question, controller.signal);
      upsertConversation(result.conversation);
      if (activeConversation.current === requestConversationId) {
        setMessages((current) => [
          ...current.filter((entry) => entry.id !== optimisticId),
          entryFromMessage(result.user_message),
          entryFromMessage(result.assistant_message),
        ]);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (activeConversation.current === requestConversationId) {
        setMessages((current) => [
          ...current,
          { id: `error-${Date.now()}`, role: "error", text: errorMessage(error) },
        ]);
        setDraft(question);
      }
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setIsLoading(false);
      }
    }
  }

  function chooseDataset(dataset: Dataset) {
    if (sameDataset(dataset.dataset_id, selectedDatasetId)) {
      setSidebarOpen(false);
      return;
    }
    if (activeConversation.current || messages.length > 0) {
      setPendingDataset(dataset);
      return;
    }
    setSelectedDatasetId(dataset.dataset_id);
    setSidebarOpen(false);
  }

  async function saveRename(title: string) {
    if (!renameTarget) return;
    setIsRenaming(true);
    setRenameError(null);
    try {
      const updated = await renameConversation(renameTarget.conversation_id, title);
      upsertConversation(updated);
      setRenameTarget(null);
    } catch (error) {
      setRenameError(errorMessage(error));
    } finally {
      setIsRenaming(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await deleteConversation(deleteTarget.conversation_id);
      setConversations((current) => current.filter((item) => item.conversation_id !== deleteTarget.conversation_id));
      if (activeConversation.current === deleteTarget.conversation_id) startNewChat(selectedDatasetId);
      setDeleteTarget(null);
    } catch (error) {
      setValidationError(errorMessage(error));
      setDeleteTarget(null);
    } finally {
      setIsDeleting(false);
    }
  }

  function datasetImported(dataset: Dataset) {
    setDatasets((current) => [...current.filter((item) => item.dataset_id !== dataset.dataset_id), dataset]);
    setUploadOpen(false);
    startNewChat(dataset.dataset_id);
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? "app-shell--collapsed" : ""}`}>
      <Sidebar
        activeConversationId={activeConversationId}
        collapsed={sidebarCollapsed}
        conversations={conversations}
        datasets={datasets}
        onClose={() => setSidebarOpen(false)}
        onDelete={setDeleteTarget}
        onNewChat={() => startNewChat()}
        onRename={(conversation) => { setRenameError(null); setRenameTarget(conversation); }}
        onSelectConversation={selectConversation}
        onSelectDataset={chooseDataset}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onUpload={() => { setSidebarOpen(false); setUploadOpen(true); }}
        open={sidebarOpen}
        selectedDatasetId={selectedDatasetId}
      />

      <div className="main-panel">
        <ChatHeader
          datasetName={datasetName}
          healthChecked={health.checked}
          isOnline={health.online}
          onOpenSidebar={() => setSidebarOpen(true)}
          title={currentConversation?.title ?? "Đoạn chat mới"}
        />
        <main className="chat-main">
          <div className="chat-column">
            {isBooting ? (
              <div className="page-loading" role="status"><LoaderCircle size={23} /> Đang tải dữ liệu…</div>
            ) : messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-icon" aria-hidden="true"><Sparkles size={23} /></div>
                <p className="eyebrow">SHOPQUERY AI</p>
                <h1>Bạn muốn khám phá điều gì?</h1>
                <p className="welcome-copy">
                  Đang sử dụng <strong>{datasetName}</strong>. Hỏi bằng tiếng Việt để phân tích dữ liệu có kiểm chứng.
                </p>
                {selectedDataset?.kind === "uploaded" ? (
                  <div className="active-dataset-summary" aria-label="Thông tin bộ dữ liệu đang dùng">
                    <span>{selectedDataset.original_filename}</span>
                    <span>{selectedDataset.file_type?.toUpperCase()}</span>
                    <span>{selectedDataset.row_count?.toLocaleString("vi-VN")} dòng</span>
                    <span>{selectedDataset.column_count} cột</span>
                    <small>{selectedDataset.columns.map((column) => `${column.source_name}: ${column.data_type}`).join(" · ")}</small>
                  </div>
                ) : null}
                <SuggestedQuestions disabled={isLoading} onSelect={submitQuestion} questions={suggestions} />
              </div>
            ) : (
              <section className="conversation" aria-label="Cuộc trò chuyện" aria-live="polite">
                {messages.map((entry) => <ChatMessage entry={entry} key={entry.id} />)}
                {isLoading ? (
                  <div className="message message--assistant loading-message" role="status">
                    <div className="assistant-mark" aria-hidden="true"><Database size={16} /></div>
                    <div className="typing-dots" aria-label="ShopQuery AI đang xử lý"><span /><span /><span /></div>
                  </div>
                ) : null}
                <div ref={conversationEnd} />
              </section>
            )}
          </div>
        </main>
        <footer className="composer-area">
          <div className="chat-column">
            <ChatInput
              datasetName={datasetName}
              disabled={isLoading || isBooting}
              onChange={updateDraft}
              onSubmit={() => submitQuestion()}
              validationError={validationError}
              value={draft}
            />
            <p className="disclaimer">AI có thể mắc lỗi. Hãy đối chiếu dữ liệu quan trọng.</p>
          </div>
        </footer>
      </div>

      {uploadOpen ? <DatasetUploadDialog onClose={() => setUploadOpen(false)} onImported={datasetImported} /> : null}
      {renameTarget ? <RenameDialog currentTitle={renameTarget.title} error={renameError} onClose={() => setRenameTarget(null)} onSave={saveRename} saving={isRenaming} /> : null}
      {deleteTarget ? <ConfirmDialog busy={isDeleting} confirmLabel="Xóa cuộc trò chuyện" danger description={`“${deleteTarget.title}” và toàn bộ tin nhắn sẽ bị xóa vĩnh viễn.`} onClose={() => setDeleteTarget(null)} onConfirm={confirmDelete} title="Xóa cuộc trò chuyện?" /> : null}
      {pendingDataset ? <ConfirmDialog confirmLabel="Bắt đầu chat mới" description={`Cuộc trò chuyện hiện tại gắn với ${datasetName}. Chuyển sang ${pendingDataset.name} sẽ bắt đầu một đoạn chat mới.`} onClose={() => setPendingDataset(null)} onConfirm={() => { const dataset = pendingDataset; setPendingDataset(null); startNewChat(dataset.dataset_id); }} title="Chuyển bộ dữ liệu?" /> : null}
    </div>
  );
}
