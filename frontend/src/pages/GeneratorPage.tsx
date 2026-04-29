import { useState, useCallback, useEffect } from 'react';
import { FolderSearch, Loader2, Zap } from 'lucide-react';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { usePdfStatus } from '../hooks/usePdfStatus';
import { useGenerateJob } from '../hooks/useGenerateJob';
import { JobProgress } from '../components/generator/JobProgress';
import { StatusTable } from '../components/generator/StatusTable';
import type { GenerateJob } from '../types';

const DEFAULT_SOURCE_DIR = import.meta.env.VITE_DEFAULT_SOURCE_DIR || '';
const DEFAULT_QUALITY = 50;

export default function GeneratorPage() {
    const [sourceDir, setSourceDir] = useState(DEFAULT_SOURCE_DIR);
    const [isCompressing, setIsCompressing] = useState(false);
    const [result, setResult] = useState<{ message: string; files: string[] } | null>(null);
    const [error, setError] = useState<string | null>(null);

    const [quality, setQuality] = useState(DEFAULT_QUALITY);

    const onCompleted = useCallback((job: GenerateJob) => {
        setResult({ message: job.message, files: job.files });
        fetchStatus();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const onFailed = useCallback((job: GenerateJob) => {
        setError(job.error ?? '生成に失敗しました。');
    }, []);

    const { currentJob, restoredSourceDir, isGenerating, isRestoredJob, startJob } = useGenerateJob(onCompleted, onFailed);

    useEffect(() => {
        if (restoredSourceDir) setSourceDir(restoredSourceDir);
    }, [restoredSourceDir]);

    const isLoading = isGenerating || isCompressing;

    const { statusItems, refetch: fetchStatus } = usePdfStatus(sourceDir, isLoading);

    const handleGenerate = async () => {
        if (!sourceDir) return;
        setError(null);
        setResult(null);
        try {
            const data = await apiClient.post<unknown, { job_id: string; status: string }>(
                API_ENDPOINTS.GENERATE,
                { source_dir: sourceDir }
            );
            startJob(data.job_id, sourceDir);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '生成に失敗しました。');
        }
    };

    const handleBatchCompress = async () => {
        setIsCompressing(true);
        setError(null);
        setResult(null);
        try {
            const data = await apiClient.post<unknown, { message: string; files: string[] }>(
                API_ENDPOINTS.BATCH_COMPRESS,
                { quality }
            );
            setResult(data);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '一括圧縮に失敗しました。');
        } finally {
            setIsCompressing(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6">
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
                <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-6 flex items-center gap-2">
                    <FolderSearch className="text-blue-600 dark:text-blue-400" />
                    PDF Generator
                </h2>

                <div className="space-y-6">
                    {/* Restored job banner */}
                    {isRestoredJob && (
                        <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-sm text-amber-800 dark:text-amber-300">
                            <Loader2 size={15} className="animate-spin shrink-0" />
                            前回の生成ジョブが実行中です — <span className="font-medium truncate">{restoredSourceDir}</span>
                        </div>
                    )}

                    {/* Source Directory Input */}
                    <div>
                        <label htmlFor="sourceDir" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            Source Directory Path
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                id="sourceDir"
                                value={sourceDir}
                                onChange={(e) => setSourceDir(e.target.value)}
                                placeholder="C:\Path\To\Images"
                                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                            />
                            <button
                                onClick={fetchStatus}
                                className="px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600 transition-colors"
                            >
                                Check Status
                            </button>
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            Enter the absolute path to the folder containing your WebP images.
                        </p>
                    </div>

                    {/* Batch Compress 用の品質スライダー（生成 API では未使用） */}
                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800 space-y-2">
                        <label htmlFor="quality" className="text-sm font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-2">
                            <Zap size={16} className="text-amber-500 fill-amber-500" />
                            Batch Compress Quality: {quality}
                            <span className="ml-auto text-xs font-normal text-gray-500 dark:text-gray-400">Lower = smaller</span>
                        </label>
                        <input
                            id="quality"
                            type="range"
                            min="10"
                            max="95"
                            step="5"
                            value={quality}
                            onChange={(e) => setQuality(parseInt(e.target.value))}
                            className="w-full h-2 bg-blue-200 dark:bg-blue-800 rounded-lg appearance-none cursor-pointer accent-blue-600"
                        />
                    </div>

                    {/* Buttons */}
                    <div className="flex flex-col gap-4">
                        <button
                            onClick={handleGenerate}
                            disabled={isLoading || !sourceDir}
                            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 dark:disabled:bg-blue-900 text-white font-bold py-4 rounded-xl shadow-lg shadow-blue-200 dark:shadow-none transition-all hover:scale-[1.01] active:scale-[0.99]"
                        >
                            {isGenerating ? <><Loader2 className="animate-spin" />Generating...</> : <><FolderSearch size={22} />Scan & Generate</>}
                        </button>

                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <span className="w-full border-t border-gray-200 dark:border-gray-700" />
                            </div>
                            <div className="relative flex justify-center text-xs uppercase">
                                <span className="bg-white dark:bg-gray-900 px-2 text-gray-500 dark:text-gray-400">Or manage existing</span>
                            </div>
                        </div>

                        <button
                            onClick={handleBatchCompress}
                            disabled={isLoading}
                            className="w-full flex items-center justify-center gap-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:bg-gray-50 dark:disabled:bg-gray-800/50 text-gray-700 dark:text-gray-300 font-semibold py-3 rounded-xl border border-gray-300 dark:border-gray-600 transition-all"
                        >
                            {isCompressing ? <Loader2 className="animate-spin" size={18} /> : <Zap size={18} className="text-amber-500" />}
                            {isCompressing ? 'Compressing...' : 'Batch Compress All Existing PDFs'}
                        </button>
                    </div>

                    {currentJob && <JobProgress job={currentJob} />}

                    {/* Error Message */}
                    {error && (
                        <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-800 animate-in fade-in slide-in-from-top-2">
                            Error: {error}
                        </div>
                    )}

                    <StatusTable items={statusItems} />

                    {/* Result Message */}
                    {result && (
                        <div className="p-4 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-lg border border-green-200 dark:border-green-800 animate-in fade-in zoom-in-95">
                            <p className="font-bold mb-2">{result.message}</p>
                            <ul className="list-disc list-inside text-sm space-y-1">
                                {result.files.map((file) => (
                                    <li key={file} className="font-medium">{file}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
