import { useState, useRef, KeyboardEvent, useEffect } from 'react';
import { X } from 'lucide-react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';

interface BulkAuthorDialogProps {
    open: boolean;
    targetCount: number;       // 選択中の書籍数
    onClose: () => void;
    onApply: (authors: string[]) => Promise<void>;
}

/**
 * 複数書籍への作者名一括設定ダイアログ。
 * 設定した作者名で選択中の全書籍を上書きする。
 */
export function BulkAuthorDialog({ open, targetCount, onClose, onApply }: BulkAuthorDialogProps) {
    const [tags, setTags] = useState<string[]>([]);
    const [input, setInput] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setTags([]);
            setInput('');
            setError(null);
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open]);

    const addTag = (value: string) => {
        const trimmed = value.trim();
        if (!trimmed) return;
        if (!tags.includes(trimmed)) {
            setTags(prev => [...prev, trimmed]);
        }
        setInput('');
    };

    const removeTag = (index: number) => {
        setTags(prev => prev.filter((_, i) => i !== index));
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            addTag(input);
        } else if (e.key === 'Backspace' && input === '' && tags.length > 0) {
            removeTag(tags.length - 1);
        }
    };

    const handleApply = async () => {
        // 入力中の未確定テキストも含める
        const finalTags = input.trim() ? [...tags, input.trim()] : tags;
        const deduped = [...new Set(finalTags)];

        setSaving(true);
        setError(null);
        try {
            await onApply(deduped);
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : '保存に失敗しました。');
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog
            open={open}
            title="作者名を一括設定"
            subtitle={`${targetCount} 冊の作者名を上書きします`}
            onClose={onClose}
            nested
        >
            <DialogBody>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    作者名
                </label>

                {/* タグ入力エリア */}
                <div
                    className="min-h-[2.5rem] w-full flex flex-wrap gap-1.5 px-2.5 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 cursor-text"
                    onClick={() => inputRef.current?.focus()}
                >
                    {tags.map((tag, i) => (
                        <span
                            key={i}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-200"
                        >
                            {tag}
                            <button
                                onClick={(e) => { e.stopPropagation(); removeTag(i); }}
                                className="hover:text-blue-600 dark:hover:text-blue-100 transition-colors"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        </span>
                    ))}
                    <input
                        ref={inputRef}
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        onBlur={() => { if (input.trim()) addTag(input); }}
                        placeholder={tags.length === 0 ? '作者名を入力（Enter で確定）' : ''}
                        className="flex-1 min-w-[8rem] text-sm bg-transparent outline-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    />
                </div>
                <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500">
                    Enter・カンマで確定、Backspace で削除
                </p>
                {error && (
                    <p className="mt-1.5 text-xs text-red-500 dark:text-red-400">{error}</p>
                )}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={handleApply} disabled={saving}>
                    {saving ? '保存中...' : '一括適用'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
