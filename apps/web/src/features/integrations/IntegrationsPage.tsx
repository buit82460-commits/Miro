"use client";
import { useState } from 'react';
import { Plug } from 'lucide-react';
import { toast } from 'sonner';
import { usePlatforms } from '@/hooks/data/useConnections';
import { useConnectionAccounts, usePauseAccount, useReconnectAccount, useRevokeAccount, useVerifyAccount } from '@/hooks/data/useConnections';
import { useTranslation } from '../../i18n/useTranslation';
import { Button, Card, StatusTag } from '../../components/miro-ui/primitives';

function badgeFor(status: string): 'success' | 'warning' | 'error' | 'neutral' | 'info' {
  if (status === 'SUPPORTED' || status === 'READY' || status === 'verified' || status === 'active') return 'success';
  if (status === 'PARTIAL' || status === 'DEGRADED' || status === 'paused') return 'warning';
  if (status === 'BLOCKED') return 'error';
  if (status === 'UNSUPPORTED' || status === 'UNAVAILABLE' || status === 'revoked') return 'neutral';
  return 'info';
}

export function IntegrationsPage() {
  const { t } = useTranslation();
  const platforms = usePlatforms();
  const accounts = useConnectionAccounts();
  const verify = useVerifyAccount();
  const pause = usePauseAccount();
  const reconnect = useReconnectAccount();
  const revoke = useRevokeAccount();
  const [actionError, setActionError] = useState('');
  const [actionOk, setActionOk] = useState('');
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);
  const [tabId, setTabId] = useState('');
  const [observed, setObserved] = useState('');

  const openEvidence = (mode: 'verify' | 'reconnect', a: { id: string; platform: string; account_id: string }) => {
    setActionError('');
    setActionOk('');
    setEvidenceFor(`${mode}:${a.id}`);
    setTabId('');
    setObserved(a.account_id);
  };

  const submitEvidence = (mode: 'verify' | 'reconnect', a: { id: string; platform: string; profile_binding_id: string; browser_instance_id: string }) => {
    setActionError('');
    setActionOk('');
    if (!tabId.trim() || !observed.trim()) {
      setActionError('Nhập tab_id + observed_account_id đọc từ tab thật đang mở.');
      return;
    }
    const evidence = {
      tab_id: tabId.trim(),
      platform_id: a.platform,
      profile_binding_id: a.profile_binding_id ?? '',
      observed_account_id: observed.trim(),
      browser_instance_id: a.browser_instance_id ?? '',
    };
    const done = {
      onSuccess: (r: { id: string; status: string }) => {
        setActionOk(`${mode === 'verify' ? 'Đã verify' : 'Đã kết nối lại'} ${r.id} → ${r.status}.`);
        setEvidenceFor(null);
      },
      onError: (e: unknown) => setActionError((e as Error).message),
    };
    if (mode === 'verify') verify.mutate({ id: a.id, evidence }, done);
    else reconnect.mutate({ id: a.id, evidence }, done);
  };

  const onPause = (id: string) => {
    setActionError('');
    pause.mutate(id, {
      onError: (e) => setActionError((e as Error).message),
    });
  };

  const onRevoke = (id: string) => {
    setActionError('');
    revoke.mutate(id, {
      onError: (e) => setActionError((e as Error).message),
    });
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-[1280px] space-y-6">
        <div>
          <h1 className="text-h1 text-[var(--color-text-primary)]">{t.nav.integrations}</h1>
          <p className="text-[14px] text-[var(--color-text-secondary)]">
            Trạng thái từ BE (<code>GET /platforms</code> + <code>GET /connections/accounts</code>).
            Nền tảng BE trả UNSUPPORTED/BLOCKED chỉ hiển thị badge, không có nút kết nối.
            Tài khoản platform thật quản lý ở Cài đặt → Kết nối (<code>/settings/connections</code>).
          </p>
        </div>

        {(platforms.isError || accounts.isError) && (
          <Card className="p-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-[var(--color-error)]">
              Chưa nối được BE (http://127.0.0.1:8770). Kiểm tra BE đang chạy rồi thử lại.
            </p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                platforms.refetch();
                accounts.refetch();
              }}
            >
              Thử lại
            </Button>
          </Card>
        )}

        {actionError && (
          <Card className="p-4">
            <p className="text-[13px] text-[var(--color-error)]">{actionError}</p>
          </Card>
        )}

        <section className="space-y-3">
          <h2 className="text-h4 text-[var(--color-text-primary)]">Nền tảng (BE registry)</h2>
          {platforms.isLoading ? (
            <p className="text-[13px] text-[var(--color-text-secondary)]">Đang tải registry nền tảng…</p>
          ) : (platforms.data?.platforms?.length ?? 0) === 0 ? (
            <p className="text-[13px] text-[var(--color-text-muted)]">BE chưa trả platform nào.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {(platforms.data?.platforms ?? []).map((p: any) => {
                const read = String(p?.tracks?.read ?? '?');
                const pub = String(p?.tracks?.publish ?? '?');
                const blocked = read === 'BLOCKED' || pub === 'BLOCKED' || read === 'UNSUPPORTED' || pub === 'UNSUPPORTED';
                return (
                  <Card key={String(p.id)} className="p-4 flex flex-col justify-between gap-3">
                    <div className="space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-secondary)]">
                            <Plug className="w-3.5 h-3.5" />
                          </div>
                          <h3 className="text-h5 text-[var(--color-text-primary)]">{String(p.name ?? p.id)}</h3>
                        </div>
                        <StatusTag tone={badgeFor(pub)}>{pub}</StatusTag>
                      </div>
                      <p className="text-[12px] text-[var(--color-text-secondary)]">
                        Đọc: <StatusTag tone={badgeFor(read)}>{read}</StatusTag>
                      </p>
                      <p className="text-[11px] text-[var(--color-text-muted)]">{String(p.runtime ?? '')}</p>
                      {blocked && (
                        <p className="text-[12px] text-[var(--color-text-secondary)]">
                          BE chưa hỗ trợ đầy đủ nền tảng này — không có nút kết nối.
                        </p>
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-h4 text-[var(--color-text-primary)]">Tài khoản kết nối (BE)</h2>
          {accounts.isLoading ? (
            <p className="text-[13px] text-[var(--color-text-secondary)]">Đang tải tài khoản…</p>
          ) : (accounts.data?.length ?? 0) === 0 ? (
            <p className="text-[13px] text-[var(--color-text-muted)]">BE chưa có tài khoản kết nối nào.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {(accounts.data ?? []).map((a) => (
                <Card key={a.id} className="p-4 flex flex-col justify-between gap-3">
                  <div className="space-y-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-h5 text-[var(--color-text-primary)]">{a.account_id}</h3>
                      <StatusTag tone={badgeFor(a.status)}>{a.status}</StatusTag>
                    </div>
                    <p className="text-[12px] text-[var(--color-text-secondary)]">
                      {a.platform} · {a.display_name || '—'}
                    </p>
                    <p className="text-[11px] font-mono-tech text-[var(--color-text-muted)]">
                      ref: {a.credential_ref ?? 'null (đã revoke)'}
                    </p>
                  </div>
                  <div className="pt-2 border-t border-[var(--color-border-subtle)] flex flex-wrap justify-end gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => openEvidence('verify', a)}
                    >
                      Xác minh
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onPause(a.id)}
                      disabled={pause.isPending}
                    >
                      Tạm dừng
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onRevoke(a.id)}
                      disabled={revoke.isPending}
                    >
                      Thu hồi
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => openEvidence('reconnect', a)}
                    >
                      Kết nối lại
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
          <p className="text-[11px] text-[var(--color-text-muted)]">
            Xác minh/cấp lại cần evidence đọc từ tab thật (tab_id + observed_account_id) — mở form bên dưới, nhập từ tab đang mở, gửi verify/reconnect.
          </p>
          {actionOk && (
            <Card className="p-3">
              <p className="text-[13px] text-[var(--color-success)]">{actionOk}</p>
            </Card>
          )}
          {evidenceFor && (
            <Card className="p-4 space-y-2">
              <p className="text-[13px] font-medium text-[var(--color-text-primary)]">
                Evidence từ tab thật ({evidenceFor})
              </p>
              <div className="flex flex-wrap gap-2">
                <input
                  type="text"
                  value={tabId}
                  onChange={(e) => setTabId(e.target.value)}
                  placeholder="tab_id (đọc từ Browser tab)"
                  className="h-9 rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] w-[220px]"
                />
                <input
                  type="text"
                  value={observed}
                  onChange={(e) => setObserved(e.target.value)}
                  placeholder="observed_account_id (đọc từ tab)"
                  className="h-9 rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] w-[260px]"
                />
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    const [mode, id] = evidenceFor.split(":");
                    const a = (accounts.data ?? []).find((x) => x.id === id);
                    if (a) submitEvidence(mode as "verify" | "reconnect", a);
                  }}
                  disabled={verify.isPending || reconnect.isPending}
                >
                  Gửi
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setEvidenceFor(null)}>
                  Hủy
                </Button>
              </div>
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}
