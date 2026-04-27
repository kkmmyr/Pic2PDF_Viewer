import { useState } from 'react';
import { useAutoFillAuthors, useToast } from '../../hooks';
import { ToastContainer } from '../reader';
import type { LibrarySource } from '../../types';

type AutoFillMode = 'missing_only' | 'unknown_only' | 'overwrite_all';

const MODE_OPTIONS: { value: AutoFillMode; label: string }[] = [
    { value: 'missing_only',  label: '未登録のみ' },
    { value: 'unknown_only',  label: '作者不明のみ' },
    { value: 'overwrite_all', label: '全件上書き' },
];

interface AutoFillAuthorsBarProps {
    source: LibrarySource;
    /** ジョブ完了時にメタデータを再取得するためのコールバック */
    onComplete: () => void;
}

/**
 * サークル名自動登録ジョブの実行制御 + 進捗表示バー。
 * LibraryPanel から切り出した独立コンポーネント。
 */
export function AutoFillAuthorsBar({ source, onComplete }: AutoFillAuthorsBarProps) {
    const [mode, setMode] = useState<AutoFillMode>('unknown_only');
    const { jobStatus, startAutoFill } = useAutoFillAuthors(source, onComplete);
    const { toasts, showToast, dismissToast } = useToast();

    const handleStart = async () => {
        try {
            await startAutoFill(mode);
        } catch (e: unknown) {
            showToast(
                e instanceof Error ? e.message : '自動登録の開始に失敗しました。Ollama と SearXNG が起動しているか確認してください。',
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
                        className="text-xs px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shrink-0"
                    >
                        サークル名自動登録
                    </button>
                    <div className="flex items-center gap-3">
                        {MODE_OPTIONS.map(({ value, label }) => (
                            <label key={value} className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none">
                                <input
                                    type="radio"
                                    name="autoFillMode"
                                    value={value}
                                    checked={mode === value}
                                    onChange={() => setMode(value)}
                                    className="accent-indigo-600"
                                />
                                {label}
                            </label>
                        ))}
                    </div>
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
                                className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                                style={{ width: `${progressPct}%` }}
                            />
                        </div>
                    </div>
                    <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">処理中…</span>
                </div>
            )}
            {jobStatus.status === 'done' && (
                <span className="text-xs text-green-600 dark:text-green-400 ml-2">
                    完了 — {jobStatus.done} 件登録、{jobStatus.skipped} 件スキップ
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
