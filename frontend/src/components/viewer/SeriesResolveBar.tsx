import { useState } from 'react';
import { useSeriesResolve, useToast } from '../../hooks';
import { ToastContainer } from '../reader';
import type { LibrarySource } from '../../types';

interface SeriesResolveBarProps {
    source: LibrarySource;
    /** ジョブ完了時にメタデータを再取得するためのコールバック */
    onComplete: () => void;
}

/**
 * シリーズ自動判定ジョブの実行 + 進捗表示バー。
 * ライブラリヘッダー直下に AutoFillAuthorsBar と並べて表示する想定。
 */
export function SeriesResolveBar({ source, onComplete }: SeriesResolveBarProps) {
    const [useGemma, setUseGemma] = useState(false);
    const { jobStatus, startResolve } = useSeriesResolve(source, onComplete);
    const { toasts, showToast, dismissToast } = useToast();

    const handleStart = async () => {
        try {
            await startResolve(useGemma);
        } catch (e: unknown) {
            showToast(
                e instanceof Error ? e.message : 'シリーズ判定の開始に失敗しました。',
                'error'
            );
        }
    };

    const isRunning = jobStatus.status === 'running';
    const progressPct = jobStatus.total > 0 ? (jobStatus.done / jobStatus.total) * 100 : 0;

    return (
        <div className="px-4 py-2 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center gap-3 min-h-[40px]">
            {!isRunning && (
                <>
                    <button
                        onClick={handleStart}
                        className="text-xs px-3 py-1 rounded bg-accent-600 hover:bg-accent-700 text-white transition-colors shrink-0"
                    >
                        シリーズ判定実行
                    </button>
                    <label className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={useGemma}
                            onChange={(e) => setUseGemma(e.target.checked)}
                            className="accent-purple-600"
                        />
                        Gemma 補助も併用（曖昧な「外伝」「番外編」を AI 判定）
                    </label>
                </>
            )}
            {isRunning && (
                <div className="flex-1 flex items-center gap-3">
                    <div className="flex-1">
                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 truncate">
                            {jobStatus.done} / {jobStatus.total} 件 — {jobStatus.current}
                        </div>
                        <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-accent-500 rounded-full transition-all duration-500"
                                style={{ width: `${progressPct}%` }}
                            />
                        </div>
                    </div>
                    <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">処理中…</span>
                </div>
            )}
            {jobStatus.status === 'done' && (
                <span className="text-xs text-green-600 dark:text-green-400 ml-2">
                    完了 — {jobStatus.created} シリーズを作成
                </span>
            )}
            {jobStatus.status === 'error' && (
                <span className="text-xs text-red-500 dark:text-red-400 truncate ml-2">
                    エラー: {jobStatus.error}
                </span>
            )}
            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </div>
    );
}
