import { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';

const FORBIDDEN_RE = /[/\\:*?"<>|]/;

interface Props {
    open: boolean;
    currentName: string;  // .pdf 拡張子あり
    onClose: () => void;
    onRename: (newName: string) => Promise<void>;
}

/**
 * PDFリネームダイアログ (Tailwind実装)。
 * 拡張子 .pdf は表示から省き、確定時に自動付加する。
 */
export function RenameDialog({ open, currentName, onClose, onRename }: Props) {
    const stem = currentName.replace(/\.pdf$/i, '');
    const [name, setName] = useState(stem);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setName(stem);
            setError(null);
            setTimeout(() => {
                inputRef.current?.focus();
                inputRef.current?.select();
            }, 50);
        }
    }, [open, stem]);

    if (!open) return null;

    const validate = (value: string): string | null => {
        if (!value.trim()) return 'ファイル名を入力してください。';
        if (FORBIDDEN_RE.test(value)) return '使用できない文字が含まれています: / \\ : * ? " < > |';
        return null;
    };

    const validationError = validate(name);
    const isSubmittable = !validationError && !loading && name.trim() !== stem;

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setName(e.target.value);
        setError(null);
    };

    const handleRename = async () => {
        const err = validate(name);
        if (err) { setError(err); return; }
        if (name.trim() === stem) { onClose(); return; }
        setLoading(true);
        try {
            await onRename(name.trim() + '.pdf');
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'リネームに失敗しました。');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && isSubmittable) handleRename();
        if (e.key === 'Escape') onClose();
    };

    const displayError = error ?? validationError;

    return (
        <div
            className="fixed inset-0 bg-black/50 z-[200] flex items-center justify-center"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-sm mx-4 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                        名前を変更
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="px-6 py-4">
                    <label htmlFor="rename-input" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        新しい名前
                    </label>
                    <div className="flex items-center gap-1">
                        <input
                            ref={inputRef}
                            id="rename-input"
                            type="text"
                            value={name}
                            onChange={handleChange}
                            onKeyDown={handleKeyDown}
                            className={`flex-1 px-3 py-2 rounded-lg border text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-blue-500 ${
                                displayError
                                    ? 'border-red-400 dark:border-red-600'
                                    : 'border-gray-300 dark:border-gray-600'
                            }`}
                        />
                        <span className="text-sm text-gray-400 dark:text-gray-500 shrink-0">.pdf</span>
                    </div>
                    <p className={`mt-1.5 text-xs min-h-[1rem] ${displayError ? 'text-red-500 dark:text-red-400' : 'text-transparent'}`}>
                        {displayError ?? '　'}
                    </p>
                </div>

                <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
                    <button
                        onClick={onClose}
                        disabled={loading}
                        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 transition-colors"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={handleRename}
                        disabled={!isSubmittable}
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 dark:disabled:bg-blue-900 rounded-lg transition-colors"
                    >
                        {loading ? '変更中...' : '変更'}
                    </button>
                </div>
            </div>
        </div>
    );
}
