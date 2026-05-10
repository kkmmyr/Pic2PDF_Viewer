/**
 * 再構築ジョブ実行中の上部バナー。
 * is_running=true のときのみ表示。検索 / 質問は 503 で待機状態になる。
 */
import { Loader2 } from 'lucide-react';

import type { RebuildStatus } from '../../features/novel_db/types';

interface Props {
    status: RebuildStatus | null;
}

function formatJobLabel(job: NonNullable<RebuildStatus['current_job']>): string {
    if (job.type === 'all') return '全書籍を再構築中';
    if (job.type === 'series') return `シリーズを再構築中 (${job.target_id})`;
    return `1 冊を再構築中 (${job.target_id})`;
}

export default function RebuildJobBanner({ status }: Props) {
    if (!status?.is_running || !status.current_job) return null;
    const job = status.current_job;
    const total = job.progress_total ?? null;
    const done = job.progress_done ?? 0;
    const queueLength = status.queued_jobs.length;

    return (
        <div
            role="status"
            className="z-overlay-bar flex items-center gap-3 px-4 py-3 bg-primary-50 dark:bg-primary-900/30 border border-primary-200 dark:border-primary-800 rounded-md text-sm text-primary-800 dark:text-primary-200"
        >
            <Loader2 className="w-5 h-5 animate-spin" />
            <div className="flex-1">
                <div className="font-medium">{formatJobLabel(job)}</div>
                {total !== null && (
                    <div className="text-xs opacity-80 mt-0.5">
                        {done}/{total} 冊処理済み
                    </div>
                )}
                {queueLength > 0 && (
                    <div className="text-xs opacity-80">待機中ジョブ: {queueLength}</div>
                )}
            </div>
            <div className="text-xs opacity-70">検索 / 質問は完了後に再開できます</div>
        </div>
    );
}
