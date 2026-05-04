import { useEffect } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import { TagsInput } from '../ui/TagsInput';
import { useDialogSubmit } from '../../hooks/useDialogSubmit';
import { useAutoFocusInput } from '../../hooks/useAutoFocusInput';
import { useTagsInput } from '../../hooks/useTagsInput';

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
    const { saving, error, handleSubmit } = useDialogSubmit(onClose);
    const t = useTagsInput();
    useAutoFocusInput(t.inputRef, open, { delay: 50 });

    useEffect(() => {
        if (open) {
            t.reset(targetCount === 1 ? [...initialTags] : []);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, targetCount, initialTags]);

    const handleApply = () => {
        handleSubmit(() => onApply(t.getFinalTags()));
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
                    tags={t.tags}
                    input={t.input}
                    inputRef={t.inputRef}
                    placeholder="タグを入力（Enter で確定）"
                    hintText="Enter・カンマで確定、Backspace で削除。空のまま適用するとタグを全て解除します。"
                    onChange={t.setInput}
                    onKeyDown={t.handleKeyDown}
                    onRemove={t.removeTag}
                    onBlur={t.handleBlur}
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
