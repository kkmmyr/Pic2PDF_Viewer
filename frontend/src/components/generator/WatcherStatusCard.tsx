import { FileArchive, FolderOpen, Loader2 } from 'lucide-react';
import { Alert } from '@/components/ui/alert';
import { formatElapsedSeconds } from '@/utils/date';
import type { DoujinWatcherState, DoujinWatcherStatus } from '@/types';

interface WatcherStatusCardProps {
    watcher: DoujinWatcherStatus | null;
}

const BADGE_CLASS: Record<DoujinWatcherState, string> = {
    idle: 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-300 border-primary-200 dark:border-primary-700',
    waiting_stable:
        'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 border-amber-200 dark:border-amber-700',
    running:
        'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-300 border-primary-200 dark:border-primary-700 animate-pulse',
    input_missing:
        'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-200 dark:border-red-700',
    disabled:
        'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 border-gray-200 dark:border-gray-600',
};

const STATE_LABEL: Record<DoujinWatcherState, string> = {
    idle: '監視中（新着なし）',
    waiting_stable: 'コピー完了待ち',
    running: '取り込み実行中',
    input_missing: '入力フォルダに接続できません',
    disabled: '自動取り込み無効',
};

/**
 * 同人誌フォルダ自動監視（watcher）の現在状態を表示するカード。
 * `watcher` が null（未取得・エラー）の間は何も描画しない。
 */
export function WatcherStatusCard({ watcher }: WatcherStatusCardProps) {
    if (!watcher) return null;

    const elapsed = formatElapsedSeconds(watcher.last_scan_at, new Date().toISOString());
    const lastScanText = elapsed ? `${elapsed}前` : '—';

    return (
        <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
                <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${BADGE_CLASS[watcher.state]}`}
                >
                    {watcher.state === 'running' && <Loader2 size={12} className="animate-spin" />}
                    {STATE_LABEL[watcher.state]}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                    最終スキャン: {lastScanText}
                </span>
            </div>

            {watcher.pending_items.length > 0 && (
                <ul className="space-y-1">
                    {watcher.pending_items.map((item) => (
                        <li
                            key={item.name}
                            className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300"
                        >
                            {item.kind === 'zip' ? (
                                <FileArchive size={14} className="text-gray-400 shrink-0" />
                            ) : (
                                <FolderOpen size={14} className="text-gray-400 shrink-0" />
                            )}
                            <span className="truncate">{item.name}</span>
                        </li>
                    ))}
                </ul>
            )}

            {watcher.retry_blocked && (
                <Alert variant="warning">
                    前回失敗したアイテムが残っています。『今すぐスキャン』で再試行できます
                </Alert>
            )}

            {watcher.state === 'input_missing' && (
                <Alert variant="warning">
                    入力フォルダ（Samba 共有）に接続できません。ネットワーク設定を確認してください。
                </Alert>
            )}
        </div>
    );
}
