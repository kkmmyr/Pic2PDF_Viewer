import { CheckCircle, XCircle, Clock } from 'lucide-react';
import type { GenerateJob } from '../../types';

interface JobProgressProps {
    job: GenerateJob;
}

/**
 * PDF 生成ジョブの進捗パネル。
 * pending / running / completed / failed で色とアイコンを切り替える。
 */
export function JobProgress({ job }: JobProgressProps) {
    const containerClass = job.status === 'failed'
        ? 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800'
        : job.status === 'completed'
            ? 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800'
            : 'bg-primary-50 border-primary-200 dark:bg-primary-900/20 dark:border-primary-800';

    const textClass = job.status === 'failed'
        ? 'text-red-700 dark:text-red-400'
        : job.status === 'completed'
            ? 'text-green-700 dark:text-green-400'
            : 'text-primary-700 dark:text-primary-400';

    return (
        <div className={`p-4 rounded-lg border animate-in fade-in slide-in-from-top-2 ${containerClass}`}>
            <div className="flex items-center gap-2 mb-2">
                {job.status === 'completed' && <CheckCircle className="text-green-600 dark:text-green-400" size={18} />}
                {job.status === 'failed' && <XCircle className="text-red-600 dark:text-red-400" size={18} />}
                {(job.status === 'pending' || job.status === 'running') && (
                    <Clock className="text-primary-600 dark:text-primary-400 animate-pulse" size={18} />
                )}
                <span className={`text-sm font-semibold ${textClass}`}>
                    {job.status === 'pending' && 'ジョブを開始中...'}
                    {job.status === 'running' && (job.current_item ? `処理中: ${job.current_item}` : '処理中...')}
                    {job.status === 'completed' && '生成完了'}
                    {job.status === 'failed' && '生成に失敗しました'}
                </span>
            </div>
            {job.status === 'running' && (
                <div className="w-full bg-primary-200 dark:bg-primary-800 rounded-full h-1.5 mt-2">
                    <div className="bg-primary-600 h-1.5 rounded-full animate-pulse w-1/2" />
                </div>
            )}
        </div>
    );
}
