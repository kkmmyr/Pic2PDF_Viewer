import { Trash2 } from 'lucide-react';

import type { BuildJob } from '@/features/novel_build/types';

export default function QueuedJobCard({
    job,
    onCancel,
}: {
    job: BuildJob;
    onCancel: (id: number) => void;
}) {
    return (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 flex items-center justify-between">
            <span className="text-sm text-gray-700 dark:text-gray-300">
                {job.target_id ?? '全冊'}
            </span>
            <button
                onClick={() => onCancel(job.id)}
                className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                title="キャンセル"
            >
                <Trash2 className="w-4 h-4" />
            </button>
        </div>
    );
}
