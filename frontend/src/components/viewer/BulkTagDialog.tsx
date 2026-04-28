import { useState, useRef, KeyboardEvent, useEffect } from 'react';
import { X } from 'lucide-react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';

interface BulkTagDialogProps {
    open: boolean;
    targetCount: number;       // 選択中の書籍数
    /** 編集開始時の既存タグ。1冊選択時のみ参考に表示 */
    initialTags?: string[];
    onClose: () => void;
    onApply: (tags: string[]) => Promise<void>;
}

/**
 * 複数書籍へのタグ一括設定ダイアログ。
 * `BulkAuthorDialog` と同じタグ入力 UI を採用。
 * 「一括適用」で選択中の全書籍のタグを上書きする（既存のタグは破棄）。
 */
export function BulkTagDialog({ open, targetCount, initialTags = [], onClose, onApply }: BulkTagDialogProps) {
    const [tags, setTags] = useState<string[]>([]);
    const [input, setInput] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            // 1冊選択時のみ既存タグを初期表示。複数冊では空から開始。
            setTags(targetCount === 1 ? [...initialTags] : []);
            setInput('');
            setError(null);
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open, targetCount, initialTags]);

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

    const subtitle = targetCount === 1
        ? '1 冊のタグを上書きします'
        : `${targetCount} 冊のタグを上書きします`;

    return (
        <Dialog
            open={open}
            title="タグを一括設定"
            subtitle={subtitle}
            onClose={onClose}
            nested
        >
            <DialogBody>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    タグ
                </label>

                <div
                    className="min-h-[2.5rem] w-full flex flex-wrap gap-1.5 px-2.5 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 cursor-text"
                    onClick={() => inputRef.current?.focus()}
                >
                    {tags.map((tag, i) => (
                        <span
                            key={i}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200"
                        >
                            {tag}
                            <button
                                onClick={(e) => { e.stopPropagation(); removeTag(i); }}
                                className="hover:text-emerald-600 dark:hover:text-emerald-100 transition-colors"
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
                        placeholder={tags.length === 0 ? 'タグを入力（Enter で確定）' : ''}
                        className="flex-1 min-w-[8rem] text-sm bg-transparent outline-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    />
                </div>
                <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500">
                    Enter・カンマで確定、Backspace で削除。空のまま適用するとタグを全て解除します。
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
