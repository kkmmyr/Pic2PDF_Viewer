import { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';

const FORBIDDEN_RE = /[/\\:*?"<>|]/;

interface Props {
    open: boolean;
    onClose: () => void;
    onCreate: (name: string) => Promise<void>;
}

/**
 * フォルダ作成ダイアログ (Tailwind実装)。
 * バリデーション（空文字・禁止文字）を行ってから onCreate を呼び出す。
 */
export function CreateFolderDialog({ open, onClose, onCreate }: Props) {
    const [name, setName] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setName('');
            setError(null);
            // 開いた瞬間にフォーカス
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open]);

    if (!open) return null;

    const validate = (value: string): string | null => {
        if (!value.trim()) return 'フォルダ名を入力してください。';
        if (FORBIDDEN_RE.test(value)) return '使用できない文字が含まれています: / \\ : * ? " < > |';
        return null;
    };

    const validationError = validate(name);
    const isSubmittable = !validationError && !loading;

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setName(e.target.value);
        setError(null);
    };

    const handleCreate = async () => {
        const err = validate(name);
        if (err) { setError(err); return; }
        setLoading(true);
        try {
            await onCreate(name.trim());
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'フォルダの作成に失敗しました。');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && isSubmittable) handleCreate();
        if (e.key === 'Escape') onClose();
    };

    const displayError = error ?? validationError;

    return (
        <div
            className="fixed inset-0 bg-black/50 z-[200] flex items-center justify-center"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-sm mx-4 border border-gray-200 dark:border-gray-700">
                {/* ヘッダー */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                        フォルダを作成
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* 本体 */}
                <div className="px-6 py-4">
                    <label htmlFor="folder-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        フォルダ名
                    </label>
                    <input
                        ref={inputRef}
                        id="folder-name"
                        type="text"
                        value={name}
                        onChange={handleChange}
                        onKeyDown={handleKeyDown}
                        placeholder="新しいフォルダ"
                        className={`w-full px-3 py-2 rounded-lg border text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 ${
                            displayError
                                ? 'border-red-400 dark:border-red-600'
                                : 'border-gray-300 dark:border-gray-600'
                        }`}
                    />
                    <p className={`mt-1.5 text-xs min-h-[1rem] ${displayError ? 'text-red-500 dark:text-red-400' : 'text-transparent'}`}>
                        {displayError ?? '　'}
                    </p>
                </div>

                {/* フッター */}
                <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
                    <button
                        onClick={onClose}
                        disabled={loading}
                        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 transition-colors"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={handleCreate}
                        disabled={!isSubmittable}
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 dark:disabled:bg-blue-900 rounded-lg transition-colors"
                    >
                        {loading ? '作成中...' : '作成'}
                    </button>
                </div>
            </div>
        </div>
    );
}
