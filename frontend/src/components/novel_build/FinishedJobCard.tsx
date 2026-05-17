import { CheckCircle, XCircle } from 'lucide-react';

import type { FinishedJob } from '../../features/novel_build/types';
import { formatSqliteUtcAsJst } from '../../utils/date';

export default function FinishedJobCard({ job }: { job: FinishedJob }) {
    const isOk = job.state === 'completed';
    const isCanceled = job.state === 'canceled';
    return (
        <div className="flex items-start gap-2 py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
            {isOk ? (
                <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
            ) : isCanceled ? (
                <XCircle className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
            ) : (
                <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            )}
            <div className="min-w-0 flex-1">
                <p className="text-sm text-gray-700 dark:text-gray-300 truncate">
                    {job.target_id ?? '全冊'}
                </p>
                {job.finished_at && (
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                        {formatSqliteUtcAsJst(job.finished_at)}
                    </p>
                )}
                {job.error_message && (
                    <p className="text-xs text-red-500 mt-0.5 truncate" title={job.error_message}>
                        {job.error_message}
                    </p>
                )}
            </div>
        </div>
    );
}
