import { CheckCircle2, Database, LoaderCircle, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChatApiError } from "./api";
import * as persistentApi from "./api";
import type { SessionInfo } from "./api";
import { createGuestClient, type GuestClient, type GuestStatus } from "./guest";
import { ChatHeader } from "./components/ChatHeader";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { ConfirmDialog, RenameDialog } from "./components/Dialogs";
import { DatasetUploadDialog } from "./components/DatasetUploadDialog";
import { GuestUploadDialog } from "./components/GuestUploadDialog";
import { Modal } from "./components/Dialogs";
import { Sidebar } from "./components/Sidebar";
import { SuggestedQuestions } from "./components/SuggestedQuestions";
import type {
  ConversationEntry,
  ConversationMessage,
  ConversationSummary,
  Dataset,
  ModelId,
  ModelOption,
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

export default function App({ account, onLogout, accessMode = "authenticated" }: { account?: SessionInfo["user"]; onLogout?: () => void; accessMode?: "guest" | "authenticated" }) {
  const isGuest = accessMode === "guest";
  const [guestStatus, setGuestStatus] = useState<GuestStatus | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const client = useMemo(() => isGuest ? createGuestClient(setGuestStatus) : persistentApi, [isGuest]);
  const guestClient = isGuest ? client as GuestClient : null;
  const releaseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [draft, setDraft] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationEntry[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [providerEnabled, setProviderEnabled] = useState(true);
  const [defaultModel, setDefaultModel] = useState<ModelId>("inetcloud-knowledge");
  const [selectedModel, setSelectedModel] = useState<ModelId>("inetcloud-knowledge");
  const [isSavingModel, setIsSavingModel] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBooting, setIsBooting] = useState(true);
  const [health, setHealth] = useState({ checked: false, online: false });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
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
  const datasetName = selectedDataset?.name ?? "bộ dữ liệu của bạn";
  const hasSources = Boolean(selectedDataset && (selectedDataset.kind === "default" ||
    (selectedDataset.table_count ?? 0) > 0 || (selectedDataset.document_count ?? 0) > 0));
  const submitUnavailableReason = !isGuest && !hasSources
    ? "Hãy tải dữ liệu lên trước khi đặt câu hỏi."
    : isGuest && guestStatus?.expired ? "Phiên dùng thử đã hết hạn. Hãy bắt đầu phiên mới."
    : isGuest && (guestStatus?.limited || (guestStatus?.remaining ?? 1) <= 0) ? "Đã hết lượt hỏi dùng thử. Đăng nhập hoặc bắt đầu lại sau."
    : isGuest && !guestStatus?.ai_enabled ? "AI đang tạm chưa được bật cho chế độ dùng thử. Bạn vẫn có thể tải và xem trước tệp."
    : !isGuest && !providerEnabled ? "Quản trị viên chưa cho phép gửi dữ liệu tới AI providers."
    : models.length > 0 && !models.find((model) => model.id === selectedModel)?.configured ? "Mô hình đã chọn chưa được cấu hình. Hãy chọn mô hình khả dụng."
    : null;
  const welcomeSubtitle = isGuest && !hasSources
    ? "Trò chuyện với AI hoặc tải bảng dữ liệu và tài liệu lên để phân tích."
    : !hasSources
    ? "Tạo bộ dữ liệu và tải bảng hoặc tài liệu lên để bắt đầu."
    : selectedDataset?.kind === "uploaded"
    ? "Đặt câu hỏi để khám phá và phân tích bộ dữ liệu của bạn."
    : "Khám phá dữ liệu, phân tích kinh doanh và tra cứu thông tin bằng AI.";
  const suggestions = useMemo(() => {
    if (!hasSources) return [];
    if (selectedDataset?.kind === "default") return DEFAULT_QUESTIONS;
    if (!selectedDataset) return [];
    if (!(selectedDataset.table_count ?? 0)) return [
      { label: "Tóm tắt tài liệu", question: "Hãy tóm tắt nội dung chính của các tài liệu trong bộ dữ liệu này.", kind: "document" as const },
    ];
    const firstColumn = selectedDataset.columns[0]?.source_name;
    const secondColumn = selectedDataset.columns[1]?.source_name;
    return [
      { label: "Kiểm tra dữ liệu", question: "Bộ dữ liệu này có tổng cộng bao nhiêu dòng?", kind: "analysis" as const },
      { label: "Phân nhóm", question: firstColumn ? `Hãy đếm số dòng theo cột ${firstColumn}.` : "Hãy phân nhóm dữ liệu theo cột đầu tiên.", kind: "analysis" as const },
      { label: "Tổng hợp", question: secondColumn ? `Hãy tổng hợp các giá trị theo cột ${secondColumn}.` : "Hãy tóm tắt các giá trị số trong dữ liệu.", kind: "analysis" as const },
    ];
  }, [selectedDataset, hasSources]);

  useEffect(() => {
    const controller = new AbortController();
    const bootstrapSequence = selectionSequence.current;
    persistentApi.getHealth(controller.signal)
      .then((result) => setHealth({ checked: true, online: result.status === "ok" }))
      .catch(() => setHealth({ checked: true, online: false }));

    Promise.all([client.getDatasets(controller.signal), client.getConversations(controller.signal), client.getModels(controller.signal)])
      .then(async ([availableDatasets, availableConversations, modelRegistry]) => {
        setDatasets(availableDatasets);
        if (!availableConversations.length) setSelectedDatasetId(availableDatasets[0]?.dataset_id ?? null);
        setModels(modelRegistry.models);
        setProviderEnabled(modelRegistry.ai_enabled ?? true);
        setDefaultModel(modelRegistry.default_model);
        if (selectionSequence.current === bootstrapSequence || !activeConversation.current) {
          setSelectedModel(modelRegistry.default_model);
        }
        setConversations(availableConversations);
        if (
          availableConversations.length > 0 &&
          selectionSequence.current === bootstrapSequence
        ) {
          const latest = availableConversations[0];
          const detail = await client.getConversation(latest.conversation_id, controller.signal);
          if (selectionSequence.current !== bootstrapSequence) return;
          activeConversation.current = latest.conversation_id;
          setActiveConversationId(latest.conversation_id);
          setSelectedDatasetId(detail.dataset_id);
          setSelectedModel(detail.model_id ?? "gemini");
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
  }, [client]);

  useEffect(() => {
    if (releaseTimer.current) clearTimeout(releaseTimer.current);
    const release = () => guestClient?.dispose();
    window.addEventListener("pagehide", release);
    const restored = (event: PageTransitionEvent) => { if (isGuest && event.persisted) window.location.reload(); };
    window.addEventListener("pageshow", restored);
    return () => {
      window.removeEventListener("pagehide", release);
      window.removeEventListener("pageshow", restored);
      releaseTimer.current = setTimeout(release, 0);
    };
  }, [guestClient, isGuest]);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, isLoading]);

  useEffect(() => () => {
    selectionSequence.current += 1;
    activeConversation.current = null;
    requestController.current?.abort();
  }, []);

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
    setSelectedModel(defaultModel);
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
      const detail = await client.getConversation(conversation.conversation_id);
      if (selectionSequence.current !== sequence) return;
      activeConversation.current = detail.conversation_id;
      setActiveConversationId(detail.conversation_id);
      setSelectedDatasetId(detail.dataset_id);
      setSelectedModel(detail.model_id ?? "gemini");
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
    if (isLoading || isBooting || isSavingModel) return;
    if (submitUnavailableReason) {
      setValidationError(submitUnavailableReason);
      return;
    }
    const requestModel = selectedModel;
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
    setIsLoading(true);
    let conversationId = activeConversation.current;
    try {
      if (!conversationId) {
        const created = await client.createConversation(selectedDataset?.dataset_id ?? null, requestModel);
        conversationId = created.conversation_id;
        activeConversation.current = conversationId;
        setActiveConversationId(conversationId);
        upsertConversation(created);
      }
    } catch (error) {
      setValidationError(errorMessage(error));
      setDraft(question);
      setIsLoading(false);
      return;
    }

    const requestConversationId = conversationId;
    const optimisticId = `pending-${Date.now()}`;
    setMessages((current) => [...current, { id: optimisticId, role: "user", text: question }]);
    setIsLoading(true);
    const controller = new AbortController();
    requestController.current = controller;

    try {
      const result = await client.sendConversationMessage(requestConversationId, question, controller.signal, requestModel);
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

  async function chooseModel(modelId: ModelId) {
    if (isLoading || isBooting || isSavingModel || modelId === selectedModel) return;
    const previous = selectedModel;
    const targetConversation = activeConversation.current;
    setSelectedModel(modelId);
    if (!targetConversation) return;
    setIsSavingModel(true);
    try {
      const updated = await client.setConversationModel(targetConversation, modelId);
      upsertConversation(updated);
    } catch (error) {
      if (activeConversation.current === targetConversation) {
        setSelectedModel(previous);
        setValidationError(errorMessage(error));
      }
    } finally {
      setIsSavingModel(false);
    }
  }

  async function saveRename(title: string) {
    if (!renameTarget) return;
    setIsRenaming(true);
    setRenameError(null);
    try {
      const updated = await client.renameConversation(renameTarget.conversation_id, title);
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
      await client.deleteConversation(deleteTarget.conversation_id);
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
    if (!activeConversation.current && messages.length === 0) {
      setSelectedDatasetId(dataset.dataset_id);
    }
    setImportNotice(`Đã cập nhật ${dataset.name} thành công.`);
  }

  function datasetDeleted(dataset: Dataset) {
    setDatasets((current) => current.filter((item) => item.dataset_id !== dataset.dataset_id));
    setConversations((current) => current.filter((item) => item.dataset_id !== dataset.dataset_id));
    if (selectedDatasetId === dataset.dataset_id) startNewChat(null);
    if (pendingDataset?.dataset_id === dataset.dataset_id) setPendingDataset(null);
    if (renameTarget?.dataset_id === dataset.dataset_id) setRenameTarget(null);
    if (deleteTarget?.dataset_id === dataset.dataset_id) setDeleteTarget(null);
    setImportNotice(`Đã xóa ${dataset.name}. Không thể hoàn tác từ giao diện.`);
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? "app-shell--collapsed" : ""}`}>
      <Sidebar
        guest={isGuest}
        account={account}
        onLogout={onLogout}
        activeConversationId={activeConversationId}
        collapsed={sidebarCollapsed}
        conversations={conversations}
        onClose={() => setSidebarOpen(false)}
        onDelete={setDeleteTarget}
        onNewChat={() => startNewChat()}
        onRename={(conversation) => { setRenameError(null); setRenameTarget(conversation); }}
        onSelectConversation={selectConversation}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onUpload={() => { setSidebarOpen(false); setUploadOpen(true); }}
        open={sidebarOpen}
      />

      <div className="main-panel">
        <ChatHeader
          onLogin={isGuest ? () => setLoginOpen(true) : undefined}
          datasets={datasets}
          healthChecked={health.checked}
          isOnline={health.online}
          onOpenSidebar={() => setSidebarOpen(true)}
          onSelectDataset={chooseDataset}
          selectedDataset={selectedDataset}
          title={currentConversation?.title ?? (isGuest ? "ShopQuery AI" : "Đoạn chat mới")}
        />
        {importNotice ? (
          <div className="import-notice" role="status">
            <CheckCircle2 size={17} />
            <span>{importNotice}</span>
            <button aria-label="Đóng thông báo import" onClick={() => setImportNotice(null)} type="button">
              <X size={16} />
            </button>
          </div>
        ) : null}
        <main className="chat-main">
          <div className="chat-column">
            {isBooting ? (
              <div className="page-loading" role="status"><LoaderCircle size={23} /> Đang tải dữ liệu…</div>
            ) : messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-mark" aria-hidden="true"><Sparkles size={22} /></div>
                <h1>{isGuest || hasSources ? "Bạn muốn hỏi gì hôm nay?" : "Không gian dữ liệu của bạn"}</h1>
                <p>{welcomeSubtitle}</p>
                {hasSources ? <SuggestedQuestions disabled={isLoading} onSelect={submitQuestion} questions={suggestions} /> :
                  <button className="primary-button" type="button" onClick={() => setUploadOpen(true)}>Thêm dữ liệu</button>}
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
              disabled={Boolean(isLoading || isBooting || isSavingModel)}
              submitUnavailableReason={submitUnavailableReason}
              placeholder={isGuest && !hasSources ? "Nhập câu hỏi để dùng thử…" : undefined}
              models={models}
              selectedModel={selectedModel}
              onModelSelect={chooseModel}
              onChange={updateDraft}
              onSubmit={() => submitQuestion()}
              validationError={validationError}
              value={draft}
            />
            {isGuest ? <div className="guest-status" aria-live="polite">
              <span>Đoạn chat tạm thời · Còn {guestStatus?.remaining ?? "…"} lượt · Refresh không khôi phục dữ liệu.</span>
              {!guestStatus?.ai_enabled ? <span>AI dùng thử chưa được bật. Bạn có thể tải và xem trước tệp tạm.</span> : null}
              {guestStatus && (guestStatus.limited || guestStatus.remaining <= 0) ? <span>Bạn đã hết ngân sách dùng thử. <button type="button" onClick={() => setLoginOpen(true)}>Đăng nhập để tiếp tục</button></span> : null}
              {guestStatus?.expired ? <span>Phiên tạm đã hết hạn. <button type="button" onClick={() => window.location.reload()}>Bắt đầu phiên mới</button></span> : null}
            </div> : null}
            <p className="disclaimer">AI có thể mắc lỗi. Hãy đối chiếu dữ liệu quan trọng.</p>
          </div>
        </footer>
      </div>

      {uploadOpen ? guestClient ? <GuestUploadDialog client={guestClient} status={guestStatus} onClose={() => setUploadOpen(false)} onImported={datasetImported} /> : <DatasetUploadDialog datasets={datasets} deletionDisabled={isLoading || isBooting || isSavingModel} onClose={() => setUploadOpen(false)} onDeleted={datasetDeleted} onImported={datasetImported} /> : null}
      {loginOpen ? <Modal className="login-modal" title="Đăng nhập ShopQuery AI" description="Mở không gian dữ liệu riêng và lưu lịch sử chat. Tệp dùng thử không tự chuyển vào tài khoản." onClose={() => setLoginOpen(false)}>
        <div className="dialog-actions"><a className="primary-button" href="/api/auth/login" onClick={() => guestClient?.dispose()}>Tiếp tục với Google</a><button className="secondary-button" type="button" onClick={() => setLoginOpen(false)}>Tiếp tục dùng thử</button></div>
      </Modal> : null}
      {renameTarget ? <RenameDialog currentTitle={renameTarget.title} error={renameError} onClose={() => setRenameTarget(null)} onSave={saveRename} saving={isRenaming} /> : null}
      {deleteTarget ? <ConfirmDialog busy={isDeleting} confirmLabel="Xóa cuộc trò chuyện" danger description={`“${deleteTarget.title}” và toàn bộ tin nhắn sẽ bị xóa vĩnh viễn.`} onClose={() => setDeleteTarget(null)} onConfirm={confirmDelete} title="Xóa cuộc trò chuyện?" /> : null}
      {pendingDataset ? <ConfirmDialog confirmLabel="Bắt đầu chat mới" description={`Cuộc trò chuyện hiện tại gắn với ${datasetName}. Chuyển sang ${pendingDataset.name} sẽ bắt đầu một đoạn chat mới.`} onClose={() => setPendingDataset(null)} onConfirm={() => { const dataset = pendingDataset; setPendingDataset(null); startNewChat(dataset.dataset_id); }} title="Chuyển bộ dữ liệu?" /> : null}
    </div>
  );
}
