import { useState, useRef, KeyboardEvent, useEffect } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import { TagsInput } from '../ui/TagsInput';
import { useDialogSubmit } from '../../hooks/useDialogSubmit';

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
 * 「一括適用」で選択中の全書籍のタグを上書きする（既存のタグは破棄）。
 */
export function BulkTagDialog({ open, targetCount, initialTags = [], onClose, onApply }: BulkTagDialogProps) {
    const [tags, setTags] = useState<string[]>([]);
    const [input, setInput] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);
    const { saving, error, handleSubmit } = useDialogSubmit(onClose);

    useEffect(() => {
        if (open) {
            setTags(targetCount === 1 ? [...initialTags] : []);
            setInput('');
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

    const handleApply = () => {
        const finalTags = input.trim() ? [...tags, input.trim()] : tags;
        const deduped = [...new Set(finalTags)];
        handleSubmit(() => onApply(deduped));
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

                <TagsInput
                    tags={tags}
                    input={input}
                    inputRef={inputRef}
                    placeholder="タグを入力（Enter で確定）"
                    chipColor="emerald"
                    hintText="Enter・カンマで確定、Backspace で削除。空のまま適用するとタグを全て解除します。"
                    onChange={setInput}
                    onKeyDown={handleKeyDown}
                    onRemove={removeTag}
                    onBlur={() => { if (input.trim()) addTag(input); }}
                />
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
