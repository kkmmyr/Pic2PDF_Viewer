import { useState } from 'react';
import { AlertCircle, CheckCircle2, Download, Loader2, RefreshCw, Users } from 'lucide-react';
import { useHitomiArrivals } from '../hooks/useHitomiArrivals';
import { useToast } from '../hooks/useToast';
import { useAsyncToast } from '../hooks/useAsyncToast';
import { HitomiArrivalCard } from '../components/hitomi/HitomiArrivalCard';
import { HitomiWatchlistDialog } from '../components/hitomi/HitomiWatchlistDialog';
import { ToastContainer } from '../components/reader/ToastContainer';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { Alert } from '../components/ui/Alert';
import { errorMessage } from '../utils/error';
import { formatDateTimeJa } from '../utils/date';
import type { RunStatus } from '../types/hitomi';

function StatusBadge({ status }: { status: RunStatus }) {
    if (status === 'ok') {
        return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300">
                <CheckCircle2 className="w-3 h-3" />
                正常
            </span>
        );
    }
    if (status === 'partial') {
        return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300">
                <AlertCircle className="w-3 h-3" />
                一部失敗
            </span>
        );
    }
    if (status === 'error') {
        return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300">
                <AlertCircle className="w-3 h-3" />
                エラー
            </span>
        );
    }
    return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
            未実行
        </span>
    );
}


export default function HitomiPage() {
    const {
        items,
        lastRunAt,
        lastRunStatus,
        lastError,
        loading,
        running,
        error,
        refresh,
        dismiss,
        dismissAll,
        runNow,
    } = useHitomiArrivals();
    const { toasts, showToast, dismissToast } = useToast();
    const runAsync = useAsyncToast(showToast);
    const [watchlistOpen, setWatchlistOpen] = useState(false);
    const [confirmDismissAllOpen, setConfirmDismissAllOpen] = useState(false);

    const errMsg = (label: string) => (e: unknown) =>
        `${label}: ${errorMessage(e, '不明')}`;

    const handleDismiss = async (id: number) => {
        await runAsync(() => dismiss(id), errMsg('既読化に失敗しました'));
    };

    const handleDismissAllConfirmed = async () => {
        setConfirmDismissAllOpen(false);
        const ok = await runAsync(async () => {
            await dismissAll();
            return true;
        }, errMsg('一括既読化に失敗しました'));
        if (ok) showToast('全件を既読化しました', 'success');
    };

    const handleRunNow = async () => {
        const stats = await runAsync(() => runNow(), errMsg('取得に失敗しました'));
        if (stats === undefined) return; // エラー時（runAsync 内で toast 済み）
        if (stats) {
            const parts = [`新着 ${stats.added} 件追加`];
            if (stats.skipped > 0) parts.push(`${stats.skipped} 件スキップ（本日既に取得済み）`);
            if (stats.errors > 0) parts.push(`エラー ${stats.errors} 件`);
            showToast(parts.join(' / '), stats.errors > 0 ? 'error' : 'success');
        } else {
            showToast('新着情報を取得しました', 'success');
        }
    };

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                        hitomi.la 新着
                    </h1>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span>最終実行: {formatDateTimeJa(lastRunAt)}</span>
                        <StatusBadge status={lastRunStatus} />
                        {lastError && (
                            <span className="text-red-500 dark:text-red-400">{lastError}</span>
                        )}
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={() => setWatchlistOpen(true)}
                        disabled={running}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                    >
                        <Users className="w-4 h-4" />
                        監視対象を編集
                    </button>
                    <button
                        onClick={refresh}
                        disabled={loading || running}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        再読み込み
                    </button>
                    <button
                        onClick={handleRunNow}
                        disabled={running}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-success-600 hover:bg-success-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Task Scheduler を待たずに監視スクリプトを実行"
                    >
                        {running ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Download className="w-4 h-4" />
                        )}
                        {running ? '取得中...' : '新着情報を取得'}
                    </button>
                    <button
                        onClick={() => setConfirmDismissAllOpen(true)}
                        disabled={items.length === 0 || running}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        全件既読化
                    </button>
                </div>
            </div>

            {error && (
                <Alert variant="error" className="mb-4">
                    {error}
                </Alert>
            )}

            {loading && items.length === 0 ? (
                <div className="flex items-center justify-center py-16 text-gray-400">
                    <Loader2 className="w-6 h-6 animate-spin" />
                </div>
            ) : items.length === 0 ? (
                <div className="text-center py-16 text-gray-500 dark:text-gray-400">
                    {lastRunStatus === 'never'
                        ? '監視がまだ一度も実行されていません。'
                        : '新着はありません。'}
                </div>
            ) : (
                <>
                    <div className="mb-3 text-sm text-gray-600 dark:text-gray-400">
                        {items.length} 件の新着
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {items.map((item) => (
                            <HitomiArrivalCard
                                key={item.id}
                                item={item}
                                onDismiss={handleDismiss}
                            />
                        ))}
                    </div>
                </>
            )}

            {watchlistOpen && (
                <HitomiWatchlistDialog
                    open
                    onClose={() => setWatchlistOpen(false)}
                    onError={(msg) => showToast(msg, 'error')}
                    onSuccess={(msg) => showToast(msg, 'success')}
                />
            )}

            <ConfirmDialog
                open={confirmDismissAllOpen}
                title="全件を既読化"
                message={`${items.length} 件すべてを既読化します。よろしいですか？`}
                confirmLabel="既読化"
                onConfirm={handleDismissAllConfirmed}
                onCancel={() => setConfirmDismissAllOpen(false)}
            />

            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </div>
    );
}
