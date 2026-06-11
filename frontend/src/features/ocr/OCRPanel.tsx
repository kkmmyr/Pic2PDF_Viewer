import { useState, useEffect, useRef } from 'react';
import { Play, Square, Terminal } from 'lucide-react';
import { useOcrStatus } from '@/hooks/useOcrStatus';
import { Alert } from '@/components/ui/Alert';
import { errorMessage } from '@/utils/error';

/**
 * Novel OCR 実行パネル (Tailwind実装)。
 * MUI を使わずTailwindのみで再実装。ダークモードは dark: クラスで対応。
 */
export const OCRPanel: React.FC = () => {
    const { status, logs, startOcr, stopOcr } = useOcrStatus();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const logEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    const handleStart = async () => {
        setLoading(true);
        setError(null);
        try {
            await startOcr();
        } catch (err: unknown) {
            setError(errorMessage(err, 'OCR開始に失敗しました。'));
        } finally {
            setLoading(false);
        }
    };

    const handleStop = async () => {
        setLoading(true);
        try {
            await stopOcr();
        } catch (err: unknown) {
            setError(errorMessage(err, 'OCR停止に失敗しました。'));
        } finally {
            setLoading(false);
        }
    };

    const isRunning = status === 'running';

    const statusBadge =
        {
            running:
                'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300 border border-primary-200 dark:border-primary-700',
            idle: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600',
            error: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 border border-red-200 dark:border-red-700',
        }[status] ??
        'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600';

    return (
        <div className="flex flex-col h-full bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            {/* ヘッダー */}
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
                <div className="flex items-center gap-3 mb-4">
                    <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">
                        Novel OCR Execution
                    </h2>
                    <span
                        className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide ${statusBadge}`}
                    >
                        {status}
                    </span>
                </div>

                <div className="flex gap-3">
                    <button
                        type="button"
                        onClick={handleStart}
                        disabled={isRunning || loading}
                        className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 dark:disabled:bg-primary-900 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                        {loading && !isRunning ? (
                            <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                        ) : (
                            <Play className="w-4 h-4 fill-white" />
                        )}
                        Start OCR
                    </button>
                    <button
                        type="button"
                        onClick={handleStop}
                        disabled={!isRunning || loading}
                        className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 dark:disabled:bg-red-900 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                        <Square className="w-4 h-4 fill-white" />
                        Stop OCR
                    </button>
                </div>

                {error && (
                    <Alert variant="error" className="mt-3">
                        {error}
                    </Alert>
                )}
            </div>

            {/* コンソールログエリア */}
            <div className="flex-1 flex flex-col min-h-0 m-4">
                <div className="flex items-center gap-2 mb-2 pb-2 border-b border-gray-700 text-gray-400 text-xs">
                    <Terminal className="w-4 h-4" />
                    <span>Console Output (ocr_service)</span>
                </div>
                <div className="flex-1 overflow-y-auto bg-[#0d1117] dark:bg-[#0d1117] rounded-lg p-3 font-mono text-sm text-[#d4d4d4] border border-gray-700">
                    {logs.length === 0 ? (
                        <span className="text-gray-500 italic">No logs available.</span>
                    ) : (
                        logs.map((line, index) => (
                            <div key={index} className="whitespace-pre-wrap leading-relaxed">
                                {line}
                            </div>
                        ))
                    )}
                    <div ref={logEndRef} />
                </div>
            </div>
        </div>
    );
};
