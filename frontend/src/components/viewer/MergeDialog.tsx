import { useState, useEffect, useRef } from 'react';

interface MergeDialogProps {
    open: boolean;
    selectedItems: string[];   // 選択中のPDFファイル名（.pdf付き）
    onClose: () => void;
    onMerge: (outputName: string) => Promise<void>;
}

const INVALID_CHARS = /[/\\:*?"<>|]/;

/**
 * PDF結合ダイアログ。
 * 選択中の書籍一覧を表示し、出力ファイル名を入力して結合を実行する。
 */
export function MergeDialog({ open, selectedItems, onClose, onMerge }: MergeDialogProps) {
    const [outputName, setOutputName] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setOutputName('');
            setError('');
            setIsLoading(false);
            setTimeout(() => inputRef.current?.focus(), 0);
        }
    }, [open]);

    const validate = (value: string): string => {
        if (!value.trim()) return 'ファイル名を入力してください。';
        if (INVALID_CHARS.test(value)) return '使用できない文字が含まれています (/ \\ : * ? " < > |)';
        return '';
    };

    const handleSubmit = async () => {
        const trimmed = outputName.trim();
        const err = validate(trimmed);
        if (err) { setError(err); return; }

        const nameWithExt = trimmed.endsWith('.pdf') ? trimmed : `${trimmed}.pdf`;
        setIsLoading(true);
        try {
            await onMerge(nameWithExt);
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : '結合に失敗しました。');
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleSubmit();
        if (e.key === 'Escape') onClose();
    };

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                    PDF を結合
                </h2>

                {/* 結合対象一覧 */}
                <div className="mb-4">
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                        結合する書籍（{selectedItems.length} 冊、上から順に結合）:
                    </p>
                    <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1 max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 bg-gray-50 dark:bg-gray-900">
                        {selectedItems.map((name, i) => (
                            <li key={name} className="flex items-center gap-2">
                                <span className="text-gray-400 dark:text-gray-500 tabular-nums w-5 text-right shrink-0">
                                    {i + 1}.
                                </span>
                                <span className="truncate">{name}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                {/* 出力ファイル名入力 */}
                <div className="mb-1">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        出力ファイル名 <span className="text-gray-400 dark:text-gray-500 font-normal">(.pdf は自動付加)</span>
                    </label>
                    <input
                        ref={inputRef}
                        type="text"
                        value={outputName}
                        onChange={(e) => { setOutputName(e.target.value); setError(''); }}
                        onKeyDown={handleKeyDown}
                        placeholder="例: merged_book"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-400 text-sm"
                    />
                </div>
                {error && (
                    <p className="text-red-500 dark:text-red-400 text-xs mt-1 mb-3">{error}</p>
                )}

                <div className="flex justify-end gap-2 mt-5">
                    <button
                        onClick={onClose}
                        disabled={isLoading}
                        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg disabled:opacity-50"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={isLoading || !outputName.trim()}
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        {isLoading && (
                            <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                        )}
                        結合
                    </button>
                </div>
            </div>
        </div>
    );
}
