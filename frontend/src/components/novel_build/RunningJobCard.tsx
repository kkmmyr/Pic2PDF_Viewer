import { Loader2 } from 'lucide-react';

import { formatSqliteUtcAsJst } from '@/utils/date';

import type { BuildJob } from '@/features/novel_build/types';

function ProgressBar({ done, total }: { done: number; total: number }) {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    return (
        <div className="mt-2">
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
                <span>
                    {done} / {total} 冊
                </span>
                <span>{pct}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                    className="bg-primary-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    );
}

function StepLabel({ step }: { step: string | null | undefined }) {
    if (!step) return null;
    const display = step.replace(/^step\s+(\d+\/\d+):\s*/i, 'Step $1: ');
    return (
        <div className="flex items-center gap-1 mt-1">
            <Loader2 className="w-3 h-3 text-primary-500 animate-spin shrink-0" />
            <p
                className="text-xs font-mono text-primary-600 dark:text-primary-400 truncate"
                title={step}
            >
                {display}
            </p>
        </div>
    );
}

function DetailLabel({ detail }: { detail: string | null | undefined }) {
    if (!detail) return null;
    return (
        <p className="text-xs text-gray-500 dark:text-gray-400 ml-4 truncate" title={detail}>
            {detail}
        </p>
    );
}

export default function RunningJobCard({ job }: { job: BuildJob }) {
    return (
        <div className="bg-white dark:bg-gray-800 border border-primary-200 dark:border-primary-800 rounded-lg p-4">
            <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-primary-500 animate-spin" />
                <span className="font-medium text-gray-900 dark:text-gray-100">
                    {job.target_id ?? '全冊'}
                </span>
            </div>
            <StepLabel step={job.current_step} />
            <DetailLabel detail={job.current_detail} />
            <ProgressBar done={job.progress_done ?? 0} total={job.progress_total ?? 1} />
            {job.started_at && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    開始: {formatSqliteUtcAsJst(job.started_at)}
                </p>
            )}
        </div>
    );
}
