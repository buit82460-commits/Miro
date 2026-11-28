"use client";
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from '@/lib/router-compat';
import {
  ArrowRight,
  ExternalLink,
  History,
  MessageSquarePlus,
  Paperclip,
  SendHorizontal,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { submitInstructionToBackend } from '../../proto-services/backend/miroBackend';
import { useMiroStore } from '../../stores/useMiroStore';
import { useTranslation } from '../../i18n/useTranslation';
import { formatTimeInZone } from '../../lib/format';
import { MiroWordmark } from '../../components/miro-shared/MiroWordmark';
import { LiveWorkspacePanel } from '../../components/miro-shared/LiveWorkspacePanel';
import { Button, StatusTag } from '../../components/miro-ui/primitives';
import { cn } from '../../lib/utils';

const SUGGESTED_PROMPTS = [
  {
    tag: 'Tìm kiếm',
    title: 'Tìm và tổng hợp video theo chủ đề',
    prompt: 'Tìm 5 video TikTok về chủ đề dưỡng sáng da và tổng hợp điểm chung.',
  },
  {
    tag: 'Lịch trình',
    title: 'Lập lịch theo dõi định kỳ',
    prompt: 'Lập lịch theo dõi 5 video mỗi sáng và báo cáo tóm tắt.',
  },
  {
    tag: 'Phân tích',
    title: 'Phân tích một video cụ thể',
    prompt: 'Phân tích video TikTok này: dán URL video vào tin nhắn.',
  },
  {
    tag: 'Xuất bản',
    title: 'Chuẩn bị bài đăng cần phê duyệt',
    prompt: 'Soạn caption kèm hashtag cho bài đăng, chờ tôi phê duyệt trước khi đăng.',
  },
];

export function AiWorkspacePage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const conversations = useMiroStore((s) => s.conversations);
  const activeConversationId = useMiroStore((s) => s.activeConversationId);
  const setActiveConversation = useMiroStore((s) => s.setActiveConversation);
  const createConversation = useMiroStore((s) => s.createConversation);
  const appendMessage = useMiroStore((s) => s.appendMessage);
  const liveMode = useMiroStore((s) => s.liveWorkspaceMode);
  const projects = useMiroStore((s) => s.projects);
  const profiles = useMiroStore((s) => s.browserProfiles);
  const settings = useMiroStore((s) => s.settings);
  const setActiveContext = useMiroStore((s) => s.setActiveContext);
  const setLastConversationRouteId = useMiroStore((s) => s.setLastConversationRouteId);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState('');
  const [selectedProfileId, setSelectedProfileId] = useState(settings.defaultProfileId || '');
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id ?? '');
  const [selectedModel, setSelectedModel] = useState('Miro Core');
  const [attachments, setAttachments] = useState<string[]>([]);
  const [chatPercent, setChatPercent] = useState(46);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [lastSentText, setLastSentText] = useState('');

  const draggingRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeConv =
    conversations.find((c) => c.id === activeConversationId) ?? conversations[0];
  const isEmpty = !activeConv || activeConv.messages.length === 0;

  useEffect(() => {
    setActiveContext({ resourceLabel: activeConv?.title ?? 'AI Workspace', projectId: selectedProjectId });
  }, [activeConv?.title, selectedProjectId, setActiveContext]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeConv?.messages.length]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setChatPercent(Math.max(32, Math.min(68, pct)));
    };
    const onUp = () => {
      draggingRef.current = false;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  // W2 run-message: gui instruction len BE (POST /tasks/run-message).
  // Thanh cong -> hien task_id/route that + link /tasks-live/{id}.
  // That bai/BE unreachable -> hien loi THAT + nut thu lai. TUYET DOI
  // khong goi mock engine, khong tu tao task/progress gia.
  const handleSend = (overridePrompt?: string) => {
    const text = (overridePrompt ?? input).trim();
    if (!text || sending) return;
    const convId = activeConv?.id ?? createConversation();
    appendMessage(convId, {
      role: 'user',
      content: text,
      attachments: attachments.length ? [...attachments] : undefined,
    });
    setInput('');
    setAttachments([]);
    setSendError(null);
    setSending(true);
    setLastSentText(text);
    void submitInstructionToBackend(text)
      .then((out) => {
        if (out?.ok && out.task_id) {
          appendMessage(convId, {
            role: 'assistant',
            content:
              `BE đã nhận việc (task ${out.task_id}, route ${out.route?.job_type ?? 'unknown'}). ` +
              `Theo dõi tiến độ thật tại /tasks-live/${out.task_id}.`,
            taskId: undefined,
            resourceLinks: [{ label: `Mở task ${out.task_id}`, route: `/tasks-live/${out.task_id}` }],
          });
          setLastConversationRouteId(convId);
          navigate(`/tasks-live/${out.task_id}`);
          return;
        }
        const detail = out?.error ?? 'unknown';
        const hint = typeof out?.hint === 'string' && out.hint ? ` Gợi ý: ${out.hint}` : '';
        const msg = `BE trả lỗi: ${detail}.${hint} Task ${out?.task_id ?? 'chưa tạo được'} — reconcile read-only, không gửi lặp.`;
        setSendError(msg);
        appendMessage(convId, { role: 'assistant', content: msg });
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : 'Gửi thất bại không rõ nguyên nhân.';
        setSendError(msg);
        appendMessage(convId, { role: 'assistant', content: msg });
      })
      .finally(() => setSending(false));
  };

  const handleAttachDemo = () => {
    const sampleName = `brief-${attachments.length + 1}.md`;
    setAttachments((prev) => [...prev, sampleName]);
    toast.info(`Đã đính kèm tệp mẫu: ${sampleName}`);
  };

  const renderComposer = (prominent = false) => (
    <div
      className={cn(
        'rounded-[14px] bg-[var(--color-surface-2)] border border-[var(--color-border-strong)]/70 transition-colors focus-within:border-[var(--color-focus-ring)]',
        prominent ? 'p-4' : 'p-3'
      )}
    >
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {attachments.map((file) => (
            <span
              key={file}
              className="inline-flex items-center gap-1.5 rounded-[4px] bg-[var(--color-surface-3)] border border-[var(--color-border)] px-2 py-0.5 text-[11px] text-[var(--color-text-secondary)]"
            >
              <span>{file}</span>
              <button
                type="button"
                aria-label={`Remove ${file}`}
                onClick={() => setAttachments((p) => p.filter((f) => f !== file))}
                className="hover:text-[var(--color-text-primary)] cursor-pointer"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <textarea
        rows={prominent ? 3 : 2}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder={t.workspace.composerPlaceholder}
        aria-label={t.workspace.composerPlaceholder}
        className="w-full resize-none bg-transparent text-[14px] leading-6 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none max-h-[160px]"
      />

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleAttachDemo}
            aria-label={t.workspace.attach}
            className="h-7 px-2 text-[12px]"
          >
            <Paperclip className="w-3.5 h-3.5" />
            {prominent && <span className="hidden sm:inline">{t.workspace.attach}</span>}
          </Button>

          <select
            aria-label="Project context"
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className={cn(
              'h-7 rounded-[6px] bg-[var(--color-surface-1)] border border-[var(--color-border)] px-2 text-[12px] text-[var(--color-text-secondary)]',
              prominent ? 'max-w-[170px]' : 'max-w-[132px]'
            )}
          >
            <option value="">Dự án: chưa chọn</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>

          <select
            aria-label="Browser profile"
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            className="h-7 rounded-[6px] bg-[var(--color-surface-1)] border border-[var(--color-border)] px-2 text-[12px] text-[var(--color-text-secondary)] max-w-[100px]"
          >
            <option value="">Profile: chưa chọn</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>

          <select
            aria-label="Model selector"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className={cn(
              'hidden sm:block h-7 rounded-[6px] bg-[var(--color-surface-1)] border border-[var(--color-border)] px-2 text-[12px] text-[var(--color-text-secondary)]',
              prominent ? 'max-w-[175px]' : 'max-w-[136px]'
            )}
          >
            <option value="Miro Core">Miro Core</option>
            <option value="Miro Fast">Miro Fast</option>
            <option value="Miro Deep Research">Miro Deep Research</option>
          </select>
        </div>

        <Button
          variant="primary"
          size="sm"
          disabled={!input.trim() || sending}
          onClick={() => handleSend()}
          className="h-8 px-3 ml-auto shrink-0"
        >
          <SendHorizontal className="w-3.5 h-3.5" />
          <span>{sending ? 'Đang gửi…' : t.workspace.send}</span>
        </Button>
      </div>
      {sendError && (
        <div className="mt-2 rounded-[8px] bg-[var(--color-error-bg)] border border-[var(--color-error)]/30 px-3 py-2 text-[12px] text-[var(--color-error)]">
          <p>{sendError}</p>
          <button
            type="button"
            onClick={() => handleSend(lastSentText)}
            disabled={sending || !lastSentText.trim()}
            className="mt-1 font-medium underline underline-offset-2 cursor-pointer disabled:opacity-50"
          >
            Thử lại
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden relative">
      {/* Collapsible Conversation History Drawer inside AI Workspace */}
      {historyOpen && (
        <aside
          aria-label={t.workspace.conversations}
          className="w-[248px] shrink-0 h-full bg-[var(--color-sidebar)] border-r border-[var(--color-border)] flex flex-col z-10"
        >
          <div className="flex items-center justify-between px-3 py-3 border-b border-[var(--color-border)]">
            <h2 className="text-h5 text-[var(--color-text-primary)]">{t.workspace.conversations}</h2>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                aria-label={t.nav.newChat}
                onClick={() => createConversation()}
                className="h-7 w-7"
              >
                <MessageSquarePlus className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Close history"
                onClick={() => setHistoryOpen(false)}
                className="h-7 w-7"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                type="button"
                onClick={() => setActiveConversation(conv.id)}
                className={cn(
                  'w-full rounded-[6px] px-2.5 py-2 text-left transition-colors cursor-pointer',
                  conv.id === activeConv?.id
                    ? 'bg-[var(--color-accent-subtle)] text-[var(--color-text-primary)] border border-[var(--color-accent-border)]/70'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-hover)] border border-transparent'
                )}
              >
                <p className="text-[13px] font-medium truncate">{conv.title}</p>
                <p className="text-[11px] font-mono-tech text-[var(--color-text-muted)] mt-0.5">
                  {conv.messages.length} tin nhắn · {formatTimeInZone(conv.updatedAt, settings.timezone)}
                </p>
              </button>
            ))}
          </div>
        </aside>
      )}

      {/* Main Conversation Column */}
      {liveMode !== 'expanded' && (
        <div
          className="flex flex-col h-full min-w-0 flex-1 overflow-hidden"
          style={
            liveMode === 'split'
              ? { flexBasis: `${chatPercent}%`, minWidth: '340px' }
              : undefined
          }
        >
          {/* Compact Workspace Sub-toolbar */}
          <div className="flex items-center justify-between gap-2 px-4 h-11 border-b border-[var(--color-border-subtle)] bg-[var(--color-canvas)] shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <Button
                variant={historyOpen ? 'subtleAccent' : 'ghost'}
                size="sm"
                onClick={() => setHistoryOpen((v) => !v)}
                className="h-7 px-2 text-[12px]"
              >
                <History className="w-3.5 h-3.5" />
                <span>{t.workspace.conversations}</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => createConversation()}
                className="h-7 px-2 text-[12px]"
              >
                <MessageSquarePlus className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t.nav.newChat}</span>
              </Button>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="text-[12px] text-[var(--color-text-muted)]">
                Tiến độ trực tiếp lấy từ BE tại /tasks-live — không có dữ liệu mô phỏng ở đây.
              </span>
            </div>
          </div>

          {/* Body: Welcome Empty State vs Active Conversation */}
          {isEmpty ? (
            <div className="flex-1 overflow-y-auto miro-welcome-atmosphere px-4 sm:px-6 py-6 flex flex-col items-center justify-center">
              <div className="w-full max-w-[780px] space-y-5">
                <div className="space-y-2.5 text-center">
                  <div className="inline-flex items-center justify-center">
                    <MiroWordmark size="lg" />
                  </div>
                  <h1 className="text-display text-[var(--color-text-primary)]">
                    {t.workspace.welcomeTitle}
                  </h1>
                  <p className="mx-auto max-w-[540px] text-[15px] leading-6 text-[var(--color-text-secondary)]">
                    {t.workspace.welcomeSubtitle}
                  </p>
                </div>

                {renderComposer(true)}

                {/* Goi y trung tinh — bam chi dien text vao input, KHONG tu chay */}
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between text-[12px] text-[var(--color-text-muted)]">
                    <span className="font-medium">{t.workspace.suggestedActions}</span>
                    <span>{t.brand.philosophy}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {SUGGESTED_PROMPTS.map((sc) => (
                      <button
                        key={sc.title}
                        type="button"
                        onClick={() => setInput(sc.prompt)}
                        className="group flex flex-col justify-between gap-2 rounded-[10px] bg-[var(--color-surface-1)]/90 border border-[var(--color-border)] p-3.5 text-left hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)] transition-colors duration-150 cursor-pointer"
                      >
                        <div className="space-y-1">
                          <p className="text-[11px] font-medium text-[var(--color-accent-text)]">
                            {sc.tag}
                          </p>
                          <p className="text-h5 text-[var(--color-text-primary)]">{sc.title}</p>
                          <p className="text-[12px] text-[var(--color-text-secondary)] line-clamp-2">
                            &quot;{sc.prompt}&quot;
                          </p>
                        </div>
                        <span className="inline-flex items-center gap-1 text-[12px] font-medium text-[var(--color-text-muted)] group-hover:text-[var(--color-text-primary)]">
                          <span>Điền vào khung chat</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Recent conversations */}
                {conversations.filter((c) => c.messages.length > 0).length > 0 && (
                  <div className="space-y-2 pt-2">
                    <p className="text-[12px] font-medium text-[var(--color-text-muted)]">
                      {t.workspace.recentConversations}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {conversations
                        .filter((c) => c.messages.length > 0)
                        .slice(0, 4)
                        .map((c) => (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => setActiveConversation(c.id)}
                            className="inline-flex items-center gap-2 rounded-[6px] bg-[var(--color-surface-1)] border border-[var(--color-border)] px-3 py-1.5 text-[12px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)] cursor-pointer"
                          >
                            <span className="truncate max-w-[220px]">{c.title}</span>
                            <span className="font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                              {c.messages.length}
                            </span>
                          </button>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <>
              {/* Active Conversation Stream */}
              <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
                <div className="mx-auto w-full max-w-[800px] space-y-6">
                  {activeConv.messages.map((msg) => {
                    if (msg.role === 'user') {
                      return (
                        <div key={msg.id} className="flex justify-end">
                          <div className="max-w-[82%] rounded-[12px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-4 py-3 space-y-1.5">
                            <p className="text-[14px] leading-6 text-[var(--color-text-primary)] whitespace-pre-wrap">
                              {msg.content}
                            </p>
                            {msg.attachments && msg.attachments.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 pt-1">
                                {msg.attachments.map((att) => (
                                  <StatusTag key={att} tone="neutral">{att}</StatusTag>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div key={msg.id} className="space-y-3">
                        <div className="flex items-center gap-2 text-[12px]">
                          <MiroWordmark size="sm" />
                          <span className="font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                            {formatTimeInZone(msg.timestamp, settings.timezone)}
                          </span>
                        </div>

                        <p className="text-[14px] leading-[23px] text-[var(--color-text-primary)] whitespace-pre-wrap">
                          {msg.content}
                        </p>

                        {msg.resourceLinks && msg.resourceLinks.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {msg.resourceLinks.map((lnk) => (
                              <Button
                                key={lnk.route}
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setLastConversationRouteId(activeConv.id);
                                  navigate(lnk.route);
                                }}
                                className="h-7 px-2.5 text-[12px] border border-[var(--color-border)]"
                              >
                                <ExternalLink className="w-3 h-3" />
                                <span>{lnk.label}</span>
                              </Button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Sticky Bottom Composer — NEVER disabled while tasks run */}
              <div className="px-4 sm:px-6 pb-4 pt-2 bg-[var(--color-canvas)] border-t border-[var(--color-border-subtle)] shrink-0">
                <div className="mx-auto w-full max-w-[800px]">{renderComposer(false)}</div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Resizable Divider (Desktop Split Mode) */}
      {liveMode === 'split' && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize workspace split"
          onMouseDown={() => {
            draggingRef.current = true;
          }}
          className="hidden lg:flex w-1.5 cursor-col-resize items-center justify-center bg-[var(--color-border-subtle)] hover:bg-[var(--color-accent)]/40 transition-colors shrink-0"
        >
          <span className="h-8 w-0.5 rounded-full bg-[var(--color-border-strong)]" />
        </div>
      )}

      {/* Universal Live Workspace */}
      {liveMode !== 'hidden' && (
        <div
          className={cn(
            liveMode === 'expanded'
              ? 'flex-1 h-full w-full'
              : 'fixed inset-0 z-30 lg:static lg:z-auto h-full lg:flex-1 min-w-0'
          )}
          style={
            liveMode === 'split'
              ? { flexBasis: `${100 - chatPercent}%` }
              : undefined
          }
        >
          <LiveWorkspacePanel className="h-full w-full" />
        </div>
      )}
    </div>
  );
}
