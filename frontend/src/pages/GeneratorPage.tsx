import { useState, useCallback, useEffect } from 'react';
import { toast } from 'sonner';
import { FolderSearch, Loader2, RefreshCw } from 'lucide-react';
import { API_ENDPOINTS } from '@/config/api';
import generateApiClient from '@/config/generate_api_client';
import { ApiError } from '@/config/api_client';
import { useGenerateJob } from '@/hooks/useGenerateJob';
import { useDoujinWatcher } from '@/hooks/useDoujinWatcher';
import { JobProgress } from '@/components/generator/JobProgress';
import { WatcherStatusCard } from '@/components/generator/WatcherStatusCard';
import { Alert } from '@/components/ui/alert';
import { errorMessage } from '@/utils/error';
import type { GenerateJob, GenerateFailedItem } from '@/types';

/** 409 の ApiError.message から `job_id=<uuid>` を抜き出す */
const JOB_ID_FROM_MESSAGE_RE = /job_id=([^)]+)\)/;

export default function GeneratorPage() {
    const [result, setResult] = useState<{
        message: string;
        files: string[];
        failed_items: GenerateFailedItem[];
    } | null>(null);
    const [error, setError] = useState<string | null>(null);

    const onCompleted = useCallback((job: GenerateJob) => {
        setResult({ message: job.message, files: job.files, failed_items: job.failed_items ?? [] });
    }, []);

    const onFailed = useCallback((job: GenerateJob) => {
        setError(job.error ?? '生成に失敗しました。');
    }, []);

    const { currentJob, isGenerating, isRestoredJob, startJob } = useGenerateJob(
        onCompleted,
        onFailed,
    );

    const { watcher } = useDoujinWatcher();

    const isLoading = isGenerating;

    // watcher がバックグラウンドでジョブを自動起動した場合、同じ JobProgress UI に反映する
    useEffect(() => {
        if (watcher?.active_job_id && watcher.active_job_id !== currentJob?.job_id) {
            startJob(watcher.active_job_id);
        }
    }, [watcher?.active_job_id, currentJob?.job_id, startJob]);

    const handleGenerate = async () => {
        setError(null);
        setResult(null);
        try {
            const data = await generateApiClient.post<unknown, { job_id: string; status: string }>(
                API_ENDPOINTS.GENERATE,
            );
            startJob(data.job_id);
        } catch (err: unknown) {
            if (err instanceof ApiError && err.status === 409) {
                toast.error('取り込みは既に実行中です');
                const match = JOB_ID_FROM_MESSAGE_RE.exec(err.message);
                if (match) {
                    startJob(match[1]);
                }
                return;
            }
            setError(errorMessage(err, '生成に失敗しました。'));
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6">
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
                <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-6 flex items-center gap-2">
                    <FolderSearch className="text-blue-600 dark:text-blue-400" />
                    取り込み
                </h2>

                <div className="space-y-6">
                    {/* Restored job banner */}
                    {isRestoredJob && (
                        <Alert
                            variant="warning"
                            icon={<Loader2 size={15} className="animate-spin shrink-0 mt-0.5" />}
                        >
                            前回の生成ジョブが実行中です
                        </Alert>
                    )}

                    {/* 自動監視ステータス */}
                    <WatcherStatusCard watcher={watcher} />

                    {/* 入力ディレクトリ説明 */}
                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
                        <p className="text-sm text-blue-800 dark:text-blue-200">
                            サーバーの入力フォルダ（Samba 共有）に WebP 画像または ZIP
                            を配置してから生成してください。新着は自動監視により自動的に取り込まれます。
                        </p>
                    </div>

                    {/* Buttons */}
                    <div className="flex flex-col gap-4">
                        <button
                            type="button"
                            onClick={handleGenerate}
                            disabled={isLoading}
                            className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 dark:disabled:bg-primary-900 text-white font-medium text-base rounded-lg transition-colors"
                        >
                            {isGenerating ? (
                                <>
                                    <Loader2 className="animate-spin" />
                                    生成中...
                                </>
                            ) : (
                                <>
                                    <RefreshCw className="w-5 h-5" />
                                    今すぐスキャン
                                </>
                            )}
                        </button>
                    </div>

                    {currentJob && <JobProgress job={currentJob} />}

                    {/* Error Message */}
                    {error && (
                        <Alert
                            variant="error"
                            className="p-4 animate-in fade-in slide-in-from-top-2"
                        >
                            エラー: {error}
                        </Alert>
                    )}

                    {/* Result Message */}
                    {result && (
                        <Alert
                            variant={result.failed_items.length > 0 ? 'warning' : 'success'}
                            className="p-4 animate-in fade-in zoom-in-95"
                        >
                            <p className="font-bold mb-2">{result.message}</p>
                            {result.files.length > 0 && (
                                <ul className="list-disc list-inside text-sm space-y-1">
                                    {result.files.map((file) => (
                                        <li key={file} className="font-medium">
                                            {file}
                                        </li>
                                    ))}
                                </ul>
                            )}
                            {result.failed_items.length > 0 && (
                                <div className="mt-3 pt-3 border-t border-current/20">
                                    <p className="font-bold mb-1 text-sm">
                                        失敗 ({result.failed_items.length}件):
                                    </p>
                                    <ul className="list-disc list-inside text-sm space-y-1">
                                        {result.failed_items.map((item) => (
                                            <li key={item.name}>
                                                <span className="font-medium">{item.name}</span>
                                                <span className="text-xs ml-2 opacity-80">
                                                    — {item.error}
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </Alert>
                    )}
                </div>
            </div>
        </div>
    );
}
