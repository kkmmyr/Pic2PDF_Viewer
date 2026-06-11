import { useState, useRef, KeyboardEvent } from 'react';
import { X } from 'lucide-react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton } from '@/components/ui/dialog';
import { errorMessage } from '@/utils/error';

interface GenreManagerDialogProps {
    open: boolean;
    genres: string[];
    onClose: () => void;
    onAdd: (name: string) => Promise<void>;
    onRemove: (name: string) => Promise<void>;
}

export function GenreManagerDialog({
    open,
    genres,
    onClose,
    onAdd,
    onRemove,
}: GenreManagerDialogProps) {
    const [input, setInput] = useState('');
    const [adding, setAdding] = useState(false);
    const [removing, setRemoving] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const handleAdd = async () => {
        const name = input.trim();
        if (!name) return;
        setError(null);
        setAdding(true);
        try {
            await onAdd(name);
            setInput('');
            inputRef.current?.focus();
        } catch (e: unknown) {
            setError(errorMessage(e, '追加に失敗しました。'));
        } finally {
            setAdding(false);
        }
    };

    const handleRemove = async (name: string) => {
        setError(null);
        setRemoving(name);
        try {
            await onRemove(name);
        } catch (e: unknown) {
            setError(errorMessage(e, '削除に失敗しました。'));
        } finally {
            setRemoving(null);
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleAdd();
        }
    };

    return (
        <Dialog
            open={open}
            title="ジャンルを管理"
            subtitle="ジャンルの追加・削除ができます"
            onClose={onClose}
            maxWidth="sm"
        >
            <DialogBody>
                <ul className="mb-4 space-y-1.5">
                    {genres.length === 0 && (
                        <li className="text-sm text-gray-400 dark:text-gray-500 py-2 text-center">
                            ジャンルがありません
                        </li>
                    )}
                    {genres.map((genre) => (
                        <li
                            key={genre}
                            className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800"
                        >
                            <span className="text-sm text-gray-800 dark:text-gray-200">
                                {genre}
                            </span>
                            <button
                                onClick={() => handleRemove(genre)}
                                disabled={removing === genre}
                                title={`「${genre}」を削除`}
                                className="p-0.5 hover:text-red-500 dark:hover:text-red-400 text-gray-400 dark:text-gray-500 transition-colors disabled:opacity-50"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </li>
                    ))}
                </ul>

                <div className="flex gap-2">
                    <input
                        ref={inputRef}
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="新しいジャンル名"
                        className="flex-1 px-2.5 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                    <button
                        onClick={handleAdd}
                        disabled={adding || !input.trim()}
                        className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        追加
                    </button>
                </div>

                {error && <p className="mt-2 text-xs text-red-500 dark:text-red-400">{error}</p>}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose}>閉じる</DialogCancelButton>
            </DialogFooter>
        </Dialog>
    );
}
