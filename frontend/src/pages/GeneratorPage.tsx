import { useState, useCallback } from 'react';
import { FolderSearch, Loader2, Zap } from 'lucide-react';
import { API_ENDPOINTS } from '@/config/api';
import generateApiClient from '@/config/generate_api_client';
import { usePdfStatus } from '@/hooks/usePdfStatus';
import { useGenerateJob } from '@/hooks/useGenerateJob';
import { JobProgress } from '@/components/generator/JobProgress';
import { StatusTable } from '@/components/generator/StatusTable';
import { Alert } from '@/components/ui/Alert';
import { errorMessage } from '@/utils/error';
import type { GenerateJob, GenerateFailedItem } from '@/types';

const DEFAULT_QUALITY = 50;

export default function GeneratorPage() {
    const [isCompressing, setIsCompressing] = useState(false);
    const [result, setResult] = useState<{
        message: string;
        files: string[];
        failed_items: GenerateFailedItem[];
    } | null>(null);
    const [error, setError] = useState<string | null>(null);

    const [quality, setQuality] = useState(DEFAULT_QUALITY);

    const onCompleted = useCallback((job: GenerateJob) => {
        setResult({ message: job.message, files: job.files, failed_items: job.failed_items ?? [] });
        // eslint-disable-next-line react-hooks/immutability -- fetchStatus は宣言順が後だが呼び出し時点では定義済み
        fetchStatus();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const onFailed = useCallback((job: GenerateJob) => {
        setError(job.error ?? '生成に失敗しました。');
    }, []);

    const { currentJob, isGenerating, isRestoredJob, startJob } = useGenerateJob(
        onCompleted,
        onFailed,
    );

    const isLoading = isGenerating || isCompressing;

    const { statusItems, refetch: fetchStatus } = usePdfStatus(isLoading);

    const handleGenerate = async () => {
        setError(null);
        setResult(null);
        try {
            const data = await generateApiClient.post<unknown, { job_id: string; status: string }>(
                API_ENDPOINTS.GENERATE,
            );
            startJob(data.job_id);
        } catch (err: unknown) {
            setError(errorMessage(err, '生成に失敗しました。'));
        }
    };

    const handleBatchCompress = async () => {
        setIsCompressing(true);
        setError(null);
        setResult(null);
        try {
            const data = await generateApiClient.post<
                unknown,
                { message: string; files: string[] }
            >(API_ENDPOINTS.BATCH_COMPRESS, { quality });
            setResult({ ...data, failed_items: [] });
        } catch (err: unknown) {
            setError(errorMessage(err, '一括圧縮に失敗しました。'));
        } finally {
            setIsCompressing(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6">
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
                <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-6 flex items-center gap-2">
                    <FolderSearch className="text-blue-600 dark:text-blue-400" />
                    PDF 生成
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

                    {/* 入力ディレクトリ説明 */}
                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
                        <p className="text-sm text-blue-800 dark:text-blue-200">
                            サーバーの入力フォルダ（Samba 共有）に WebP 画像または ZIP
                            を配置してから生成してください。
                        </p>
                    </div>

                    {/* Batch Compress 用の品質スライダー（生成 API では未使用） */}
                    <div className="p-4 bg-primary-50 dark:bg-primary-900/20 rounded-lg border border-primary-100 dark:border-primary-800 space-y-2">
                        <label
                            htmlFor="quality"
                            className="text-sm font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-2"
                        >
                            <Zap size={16} className="text-amber-500 fill-amber-500" />
                            一括圧縮 品質: {quality}
                            <span className="ml-auto text-xs font-normal text-gray-500 dark:text-gray-400">
                                小さいほどファイルサイズ小
                            </span>
                        </label>
                        <input
                            id="quality"
                            type="range"
                            min="10"
                            max="95"
                            step="5"
                            value={quality}
                            onChange={(e) => setQuality(parseInt(e.target.value))}
                            className="w-full h-2 bg-primary-200 dark:bg-primary-800 rounded-lg appearance-none cursor-pointer accent-primary-600"
                        />
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
                                    <FolderSearch className="w-5 h-5" />
                                    スキャン &amp; 生成
                                </>
                            )}
                        </button>

                        <button
                            type="button"
                            onClick={fetchStatus}
                            disabled={isLoading}
                            className="px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600 transition-colors"
                        >
                            状態確認
                        </button>

                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <span className="w-full border-t border-gray-200 dark:border-gray-700" />
                            </div>
                            <div className="relative flex justify-center text-xs uppercase">
                                <span className="bg-white dark:bg-gray-900 px-2 text-gray-500 dark:text-gray-400">
                                    または既存 PDF を管理
                                </span>
                            </div>
                        </div>

                        <button
                            onClick={handleBatchCompress}
                            disabled={isLoading}
                            className="w-full flex items-center justify-center gap-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:bg-gray-50 dark:disabled:bg-gray-800/50 text-gray-700 dark:text-gray-300 font-semibold py-3 rounded-xl border border-gray-300 dark:border-gray-600 transition-all"
                        >
                            {isCompressing ? (
                                <Loader2 className="animate-spin" size={18} />
                            ) : (
                                <Zap size={18} className="text-amber-500" />
                            )}
                            {isCompressing ? '圧縮中...' : '既存 PDF を一括圧縮'}
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

                    <StatusTable items={statusItems} />

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
