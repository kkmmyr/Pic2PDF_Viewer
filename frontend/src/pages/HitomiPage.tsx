import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import { useHitomiArrivals } from '../hooks/useHitomiArrivals';
import { HitomiArrivalCard } from '../components/hitomi/HitomiArrivalCard';
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

function formatDateTime(iso: string | null): string {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleString('ja-JP');
    } catch {
        return iso;
    }
}

export default function HitomiPage() {
    const { items, lastRunAt, lastRunStatus, lastError, loading, error, refresh, dismiss, dismissAll } =
        useHitomiArrivals();

    const handleDismiss = async (id: number) => {
        try {
            await dismiss(id);
        } catch (e) {
            alert(`既読化に失敗しました: ${e instanceof Error ? e.message : '不明'}`);
        }
    };

    const handleDismissAll = async () => {
        if (items.length === 0) return;
        if (!confirm(`${items.length} 件すべてを既読化します。よろしいですか？`)) return;
        try {
            await dismissAll();
        } catch (e) {
            alert(`一括既読化に失敗しました: ${e instanceof Error ? e.message : '不明'}`);
        }
    };

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">hitomi.la 新着</h1>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span>最終実行: {formatDateTime(lastRunAt)}</span>
                        <StatusBadge status={lastRunStatus} />
                        {lastError && <span className="text-red-500 dark:text-red-400">{lastError}</span>}
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={refresh}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        再読み込み
                    </button>
                    <button
                        onClick={handleDismissAll}
                        disabled={items.length === 0}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        全件既読化
                    </button>
                </div>
            </div>

            {error && (
                <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300">
                    {error}
                </div>
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
                        {items.map(item => (
                            <HitomiArrivalCard key={item.id} item={item} onDismiss={handleDismiss} />
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
