"use client";
import { useState } from 'react';
import { useNavigate } from '@/lib/router-compat';
import { SendHorizontal, Sparkles } from 'lucide-react';
import { useMiroStore } from '../../stores/useMiroStore';
import { useTranslation } from '../../i18n/useTranslation';
import { useBeTasks } from '@/hooks/data/useRuntime';
import { Button, Drawer } from '../miro-ui/primitives';

export function ContextualAiAssistantDrawer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const open = useMiroStore((s) => s.aiAssistantOpen);
  const setOpen = useMiroStore((s) => s.setAiAssistantOpen);
  const activeContext = useMiroStore((s) => s.activeContext);
  const beTasks = useBeTasks(4, 5000);

  const [input, setInput] = useState('');

  const handleSubmit = (text?: string) => {
    const prompt = (text ?? input).trim();
    if (!prompt) return;
    // Gợi ý chỉ điền text vào input — không tự execute mock.
    setInput(prompt);
  };

  const handleSend = () => {
    const prompt = input.trim();
    if (!prompt) return;
    // BE chưa hỗ trợ: gửi prompt trực tiếp từ drawer — điều hướng sang Tasks để tạo qua POST /tasks.
    setOpen(false);
    navigate('/tasks');
  };

  const quickSuggestions =
    activeContext.resourceKind === 'media'
      ? ['Mô tả video này để tạo task phân tích trên BE', 'Soạn nội dung bản nháp để tạo task trên BE']
      : activeContext.resourceKind === 'schedule'
        ? ['Mô tả lịch trình này để tạo task kiểm tra trên BE']
        : ['Mô tả tác vụ cần tạo trên BE', 'Soạn nội dung để tạo task mới'];

  return (
    <Drawer
      open={open}
      onClose={() => setOpen(false)}
      title={t.header.aiAssistant}
      subtitle="Hoạt động gắn liền tài nguyên bạn đang mở"
      widthClass="w-full sm:w-[400px]"
    >
      <div className="flex flex-col h-full justify-between gap-4">
        <div className="space-y-4">
          <div className="rounded-[8px] bg-[var(--color-surface-2)] border border-[var(--color-border)] p-3 space-y-1 text-[12px]">
            <p className="text-[11px] font-medium uppercase tracking-[0.04em] text-[var(--color-text-muted)]">
              Ngữ cảnh đang gắn kết
            </p>
            <p className="text-[13px] font-medium text-[var(--color-text-primary)]">
              {activeContext.resourceLabel ?? 'Toàn bộ Workspace hiện tại'}
            </p>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              Gợi ý chỉ điền text vào ô nhập — không tự chạy tác vụ.
            </p>
          </div>

          <div className="space-y-1.5">
            <p className="text-[12px] font-medium text-[var(--color-text-secondary)]">Gợi ý nhanh theo ngữ cảnh</p>
            <div className="flex flex-col gap-1.5">
              {quickSuggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => handleSubmit(s)}
                  className="flex items-center gap-2 rounded-[6px] bg-[var(--color-surface-1)] border border-[var(--color-border)] px-3 py-2 text-left text-[12px] text-[var(--color-text-secondary)] hover:bg-[var(--color-hover)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer"
                >
                  <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent-text)] shrink-0" />
                  <span>{s}</span>
                </button>
              ))}
            </div>
          </div>

          {(beTasks.data ?? []).length > 0 && (
            <div className="space-y-2">
              <p className="text-[12px] font-medium text-[var(--color-text-secondary)]">
                Tác vụ BE gần đây ({(beTasks.data ?? []).length})
              </p>
              {(beTasks.data ?? []).map((tk) => (
                <button
                  key={tk.id}
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    navigate('/tasks');
                  }}
                  className="w-full rounded-[8px] bg-[var(--color-surface-1)] border border-[var(--color-border)] p-3 space-y-1 text-left text-[12px] hover:bg-[var(--color-hover)] transition-colors cursor-pointer"
                >
                  <p className="font-mono-tech text-[var(--color-text-primary)]">{tk.id}</p>
                  <p className="text-[var(--color-text-secondary)]">{String(tk.status ?? '')}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="rounded-[12px] bg-[var(--color-surface-2)] border border-[var(--color-border)] p-2.5 space-y-2"
        >
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              activeContext.resourceLabel
                ? `Soạn nội dung về "${activeContext.resourceLabel}"...`
                : 'Nhập yêu cầu cho Miro...'
            }
            className="w-full resize-none bg-transparent text-[13px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
          />
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-[var(--color-text-muted)]">Gửi chuyển sang trang Tác vụ (BE)</span>
            <Button type="submit" variant="primary" size="sm" disabled={!input.trim()}>
              <SendHorizontal className="w-3.5 h-3.5" />
              <span>{t.workspace.send}</span>
            </Button>
          </div>
        </form>
      </div>
    </Drawer>
  );
}
