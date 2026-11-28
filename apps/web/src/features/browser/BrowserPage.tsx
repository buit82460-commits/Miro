"use client";
import {
  Globe as Chrome,
  RefreshCw,
  Search,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useRuntimeStatus } from '@/hooks/data/useRuntime';
import { useTranslation } from '../../i18n/useTranslation';
import { Button, Card } from '../../components/miro-ui/primitives';
import { RuntimeBridgeBanner } from '../../components/miro-shared/RuntimeBridgeBanner';

export function BrowserPage() {
  const { t } = useTranslation();
  const status = useRuntimeStatus(10_000);
  const [search, setSearch] = useState('');

  const tabs = useMemo(
    () => status.data?.bridge?.tabs ?? [],
    [status.data]
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return tabs;
    const q = search.toLowerCase();
    return tabs.filter(
      (tb) =>
        String(tb.title ?? '').toLowerCase().includes(q) ||
        String(tb.url ?? '').toLowerCase().includes(q) ||
        String(tb.browser ?? '').toLowerCase().includes(q)
    );
  }, [tabs, search]);

  return (
    <div className="h-full flex flex-col p-4 sm:p-6 gap-4 overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-h1 text-[var(--color-text-primary)]">{t.nav.browser}</h1>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            Tabs live duy nhất từ BE <code>GET /tasks/runtime/status</code> (bridge.tabs).
            BE chưa hỗ trợ: điều khiển/ngắt tab, điều hướng thủ công.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-[260px]">
            <Search className="w-3.5 h-3.5 text-[var(--color-text-muted)] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm tab..."
              className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] pl-8 pr-3 text-[13px] text-[var(--color-text-primary)] focus:border-[var(--color-focus-ring)] focus:outline-none"
            />
          </div>
          <Button variant="secondary" size="sm" onClick={() => status.refetch()} disabled={status.isFetching}>
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Tải lại</span>
          </Button>
        </div>
      </div>

      <div className="shrink-0">
        <RuntimeBridgeBanner />
      </div>

      {status.isLoading ? (
        <p className="text-[13px] text-[var(--color-text-secondary)]">Đang tải tabs live từ BE…</p>
      ) : status.isError ? (
        <Card className="p-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px] text-[var(--color-error)]">
            Chưa nối được BE (http://127.0.0.1:8770). Kiểm tra BE đang chạy rồi thử lại.
          </p>
          <Button variant="secondary" size="sm" onClick={() => status.refetch()}>
            Thử lại
          </Button>
        </Card>
      ) : filtered.length === 0 ? (
        <Card className="p-8 text-center space-y-2">
          <p className="text-h4 text-[var(--color-text-primary)]">Chưa có tab live từ BE</p>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            BE trả bridge.tabs rỗng. Mở tab qua bridge rồi tải lại.
          </p>
        </Card>
      ) : (
        <div className="flex-1 overflow-auto rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)]">
          <table className="w-full border-collapse text-left min-w-[720px]">
            <thead className="sticky top-0 bg-[var(--color-surface-2)] border-b border-[var(--color-border)]">
              <tr className="h-[36px] text-[12px] font-medium text-[var(--color-text-secondary)]">
                <th className="px-3">Trình duyệt</th>
                <th className="px-3">Tab</th>
                <th className="px-3">Tiêu đề</th>
                <th className="px-3">URL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border-subtle)]">
              {filtered.map((tb, idx) => (
                <tr key={`${tb.browser}-${tb.tab}-${idx}`} className="h-[52px]">
                  <td className="px-3">
                    <p className="text-[13px] font-medium text-[var(--color-text-primary)]">{tb.browser}</p>
                  </td>
                  <td className="px-3 font-mono-tech text-[12px] text-[var(--color-text-secondary)]">
                    {tb.tab}
                  </td>
                  <td className="px-3 text-[13px] text-[var(--color-text-primary)]">
                    <span className="flex items-center gap-2">
                      <Chrome className="w-3.5 h-3.5 text-[var(--color-text-muted)] shrink-0" />
                      <span className="truncate block max-w-[280px]">{tb.title || '—'}</span>
                    </span>
                  </td>
                  <td className="px-3 font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                    <span className="truncate block max-w-[320px]">{tb.url || '—'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
