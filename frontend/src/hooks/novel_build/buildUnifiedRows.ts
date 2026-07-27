import type { BuildMode } from '@/features/novel_build/types';
import type { useNovelBuildQueue } from '@/hooks/novel_build/useNovelBuildQueue';
import type { useOcrStatus } from '@/hooks/useOcrStatus';

export interface UnifiedRow {
    key: string;
    type: string;
    target: string;
    state: string;
    stateClass: string;
    time?: string;
}

function modeLabel(mode?: BuildMode): string {
    if (mode === 'generate_contexts') return 'コンテキスト生成';
    if (mode === 'generate_relations') return '関係グラフ生成';
    return 'Full Build';
}

export function buildUnifiedRows(
    ocrStatus: ReturnType<typeof useOcrStatus>['status'],
    status: ReturnType<typeof useNovelBuildQueue>['status'],
): UnifiedRow[] {
    const rows: UnifiedRow[] = [];

    if (ocrStatus === 'running') {
        rows.push({
            key: 'ocr-running',
            type: 'OCR',
            target: '-',
            state: '実行中',
            stateClass:
                'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300',
        });
    } else if (ocrStatus === 'error') {
        rows.push({
            key: 'ocr-error',
            type: 'OCR',
            target: '-',
            state: 'エラー',
            stateClass: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
        });
    }

    if (status.current_job) {
        const job = status.current_job;
        rows.push({
            key: `build-running-${job.id}`,
            type: modeLabel(job.mode),
            target: job.target_id ?? '全冊',
            state: '実行中',
            stateClass:
                'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300',
            time: job.started_at ?? undefined,
        });
    }

    for (const job of status.queued_jobs) {
        rows.push({
            key: `build-queued-${job.id}`,
            type: modeLabel(job.mode),
            target: job.target_id ?? '全冊',
            state: '待機中',
            stateClass: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
            time: job.enqueued_at ?? undefined,
        });
    }

    for (const job of status.recent_finished) {
        const state =
            { completed: '完了', failed: '失敗', canceled: 'キャンセル' }[job.state] ?? '完了';
        const stateClass =
            {
                completed: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
                failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
                canceled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
            }[job.state] ?? 'bg-gray-100 text-gray-600';
        rows.push({
            key: `build-finished-${job.id}`,
            type: modeLabel(job.mode),
            target: job.target_id ?? '全冊',
            state,
            stateClass,
            time: job.finished_at ?? undefined,
        });
    }

    return rows;
}
