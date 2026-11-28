"use client";
import { useNavigate } from '@/lib/router-compat';
import { CheckCircle2, ExternalLink, Maximize2, Minimize2, X } from 'lucide-react';
import { useMiroStore } from '../../stores/useMiroStore';
import { useTranslation } from '../../i18n/useTranslation';
import { useBeEvents, useBeTask } from '@/hooks/data/useRuntime';
import { RuntimeService } from '@/lib/services/runtime.service';
import { Button, SegmentedTabs, TaskStatusBadge } from '../miro-ui/primitives';
import { ResourceKindIcon } from './LiveTaskCard';
import { cn } from '../../lib/utils';

// Panel hien thi tien do that tu BE (W1/W2: GET /tasks/{id}, /events).
// Nguyen tac cung: KHONG progress/steps/bang chung mo phong.
// Khong co du lieu -> empty state "Chua co tien do tu BE".
export function LiveWorkspacePanel({ className }: { className?: string }) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const liveMode = useMiroStore((s) => s.liveWorkspaceMode);
  const liveTaskId = useMiroStore((s) => s.liveWorkspaceTaskId);
  const activeTab = useMiroStore((s) => s.liveWorkspaceTab);
  const setLiveWorkspace = useMiroStore((s) => s.setLiveWorkspace);
  const setLiveWorkspaceTab = useMiroStore((s) => s.setLiveWorkspaceTab);

  const taskQuery = useBeTask(liveTaskId ?? undefined, 2000);
  const eventsQuery = useBeEvents(liveTaskId ?? undefined, 1500);

  if (liveMode === 'hidden') return null;

  const beTask = taskQuery.data ?? null;
  const beEvents = eventsQuery.data ?? [];
  const beError = taskQuery.isError ? RuntimeService.errMessage(taskQuery.error) : null;

  const handleOpenFull = () => {
    if (beTask) navigate(`/tasks-live/${encodeURIComponent(beTask.id)}`);
    else navigate('/tasks-live');
  };

  return (
    <section
      aria-label="Universal Live Workspace"
      className={cn(
        'flex flex-col h-full bg-[var(--color-sidebar)] border-l border-[var(--color-border)] min-w-0',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-[var(--color-border)] shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-accent-text)]">
            <ResourceKindIcon kind="browser" className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-h5 text-[var(--color-text-primary)] truncate">
                {t.workspace.liveWorkspace}
              </h2>
              {beTask && <TaskStatusBadge status={(beTask.status as 'running') ?? 'queued'} />}
            </div>
            <p className="text-[12px] text-[var(--color-text-muted)] truncate">
              {beTask ? `Task ${beTask.id} · ${beTask.status}` : 'Dữ liệu trực tiếp từ BE'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            title={t.workspace.openFullPage}
            aria-label={t.workspace.openFullPage}
            onClick={handleOpenFull}
          >
            <ExternalLink className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title={liveMode === 'expanded' ? t.workspace.collapse : t.workspace.expand}
            aria-label={liveMode === 'expanded' ? t.workspace.collapse : t.workspace.expand}
            onClick={() => setLiveWorkspace(liveMode === 'expanded' ? 'split' : 'expanded')}
          >
            {liveMode === 'expanded' ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title={t.workspace.hideLiveWorkspace}
            aria-label={t.workspace.hideLiveWorkspace}
            onClick={() => setLiveWorkspace('hidden')}
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Tabs Bar */}
      <div className="px-4 py-2.5 border-b border-[var(--color-border)] space-y-2.5 shrink-0 bg-[var(--color-surface-1)]/50">
        <SegmentedTabs
          value={activeTab}
          onChange={setLiveWorkspaceTab}
          items={[
            { value: 'workspace', label: 'Workspace' },
            { value: 'activity', label: t.common.activity, count: beEvents.length },
            { value: 'evidence', label: t.common.evidence },
            { value: 'result', label: t.common.result },
          ]}
        />
      </div>

      {/* Tab Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {!liveTaskId ? (
          <div className="rounded-[10px] border border-dashed border-[var(--color-border)] p-6 text-center space-y-2">
            <p className="text-[13px] font-medium text-[var(--color-text-primary)]">
              Chưa chọn task BE nào
            </p>
            <p className="text-[12px] text-[var(--color-text-muted)]">
              Gửi instruction từ AI Workspace hoặc mở một task tại /tasks-live để xem tiến độ thật.
            </p>
            <Button variant="secondary" size="sm" onClick={() => navigate('/tasks-live')}>
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Mở /tasks-live</span>
            </Button>
          </div>
        ) : taskQuery.isLoading ? (
          <p className="text-[13px] text-[var(--color-text-muted)]">Đang tải task từ BE…</p>
        ) : taskQuery.isError || !beTask ? (
          <div className="rounded-[10px] bg-[var(--color-error-bg)] border border-[var(--color-error)]/30 p-4 space-y-2">
            <p className="text-[13px] text-[var(--color-error)]">
              {beError?.status === undefined
                ? 'Chưa nối được BE (http://127.0.0.1:8770 unreachable). Kiểm tra BE rồi thử lại.'
                : `BE lỗi (${beError.status}${beError.code ? `: ${beError.code}` : ''}): ${beError.message}`}
            </p>
            <Button variant="secondary" size="sm" onClick={() => { void taskQuery.refetch(); void eventsQuery.refetch(); }}>
              <span>Thử lại</span>
            </Button>
          </div>
        ) : (
          <>
            {activeTab === 'workspace' && (
              <div className="space-y-3">
                <div className="rounded-[10px] bg-[var(--color-surface-1)] border border-[var(--color-border)] p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-h5 text-[var(--color-text-primary)]">Task {beTask.id}</span>
                    <span className="text-[12px] font-mono-tech text-[var(--color-text-muted)]">
                      {beTask.status}
                      {beTask.revision !== undefined ? ` · rev ${beTask.revision}` : ''}
                    </span>
                  </div>
                  {beTask.error ? (
                    <p className="text-[12px] text-[var(--color-error)]">
                      {beTask.error.code}: {beTask.error.message}
                    </p>
                  ) : null}
                  <Button variant="primary" size="sm" onClick={handleOpenFull}>
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Mở chi tiết /tasks-live/{beTask.id}</span>
                  </Button>
                </div>
                {eventsQuery.isLoading ? (
                  <p className="text-[13px] text-[var(--color-text-muted)]">Đang tải events từ BE…</p>
                ) : eventsQuery.isError ? (
                  <div className="rounded-[8px] bg-[var(--color-error-bg)] border border-[var(--color-error)]/30 px-3 py-2 text-[12px] text-[var(--color-error)]">
                    Không tải được events BE.{' '}
                    <button
                      type="button"
                      onClick={() => { void eventsQuery.refetch(); }}
                      className="font-medium underline underline-offset-2 cursor-pointer"
                    >
                      Thử lại
                    </button>
                  </div>
                ) : beEvents.length === 0 ? (
                  <p className="text-[13px] text-[var(--color-text-muted)]">
                    Chưa có tiến độ từ BE — task mới tạo hoặc chưa phát sinh sự kiện.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {beEvents.slice(0, 10).map((e) => (
                      <li
                        key={e.sequence}
                        className="rounded-[8px] bg-[var(--color-surface-1)] border border-[var(--color-border)] p-3 text-[12px]"
                      >
                        <div className="flex items-center justify-between font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                          <span>#{e.sequence} · {e.type}</span>
                          <span>{e.timestamp}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {activeTab === 'activity' && (
              <div className="space-y-2">
                {eventsQuery.isLoading ? (
                  <p className="text-[13px] text-[var(--color-text-muted)]">Đang tải events từ BE…</p>
                ) : eventsQuery.isError ? (
                  <div className="rounded-[8px] bg-[var(--color-error-bg)] border border-[var(--color-error)]/30 px-3 py-2 text-[12px] text-[var(--color-error)]">
                    Không tải được events BE.{' '}
                    <button
                      type="button"
                      onClick={() => { void eventsQuery.refetch(); }}
                      className="font-medium underline underline-offset-2 cursor-pointer"
                    >
                      Thử lại
                    </button>
                  </div>
                ) : beEvents.length === 0 ? (
                  <p className="text-[13px] text-[var(--color-text-muted)]">Chưa có sự kiện thực thi.</p>
                ) : (
                  beEvents.map((e) => (
                    <div
                      key={e.sequence}
                      className="rounded-[8px] bg-[var(--color-surface-1)] border border-[var(--color-border)] p-3 space-y-1"
                    >
                      <div className="flex items-center justify-between text-[11px] font-mono-tech text-[var(--color-text-muted)]">
                        <span>{e.type}</span>
                        <span>{e.timestamp}</span>
                      </div>
                      <p className="text-[13px] text-[var(--color-text-primary)]">
                        #{e.sequence}
                      </p>
                    </div>
                  ))
                )}
              </div>
            )}

            {activeTab === 'evidence' && (
              <div className="space-y-2.5">
                {beTask.evidence ? (
                  <pre className="rounded-[8px] bg-[var(--color-surface-1)] border border-[var(--color-border)] p-3 text-[12px] overflow-auto">
                    {JSON.stringify(beTask.evidence, null, 2).slice(0, 2000)}
                  </pre>
                ) : (
                  <p className="text-[13px] text-[var(--color-text-muted)]">
                    Chưa có bằng chứng từ BE — evidence chỉ hiện khi task trả về evidence thật.
                  </p>
                )}
              </div>
            )}

            {activeTab === 'result' && (
              <div className="rounded-[10px] bg-[var(--color-surface-1)] border border-[var(--color-border)] p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" />
                  <h3 className="text-h5 text-[var(--color-text-primary)]">Kết quả tác vụ</h3>
                </div>
                <p className="text-[13px] text-[var(--color-text-secondary)]">
                  {beTask.status === 'completed'
                    ? 'Task hoàn tất trên BE — xem evidence và events tại trang chi tiết.'
                    : beTask.error
                      ? `${beTask.error.code}: ${beTask.error.message}`
                      : 'Chưa có tiến độ từ BE — task đang chờ xử lý hoặc chưa phát sinh sự kiện.'}
                </p>
                <Button variant="primary" size="sm" onClick={handleOpenFull}>
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>{t.workspace.openInWorkspace}</span>
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
