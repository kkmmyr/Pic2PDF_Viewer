import { useState, useEffect } from 'react';
import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/ui/searchable-select';
import { TagsInput } from '@/components/ui/tags-input';
import { useDialogSubmit } from '@/hooks/library/useDialogSubmit';
import { useAutoFocusInput } from '@/hooks/useAutoFocusInput';
import { useTagsInput } from '@/hooks/useTagsInput';

interface BulkAuthorDialogProps {
    open: boolean;
    targetCount: number; // 選択中の書籍数
    /** 既存の作者一覧。空配列なら「既存から選択」モードは無効 */
    allAuthors: string[];
    onClose: () => void;
    onApply: (authors: string[]) => Promise<void>;
}

type Mode = 'existing' | 'new';

/**
 * 複数書籍への作者名一括設定ダイアログ。
 *
 * - 既存モード: SearchableSelect から 1 名選択
 * - 新規モード: chip 入力で複数の作者名を Enter / カンマ区切りで追加
 */
export function BulkAuthorDialog({
    open,
    targetCount,
    allAuthors,
    onClose,
    onApply,
}: BulkAuthorDialogProps) {
    const noExistingAuthors = allAuthors.length === 0;
    const [mode, setMode] = useState<Mode>(noExistingAuthors ? 'new' : 'existing');
    const [selectedExisting, setSelectedExisting] = useState<string>('');
    const { saving, error, setError, handleSubmit } = useDialogSubmit(onClose);
    const t = useTagsInput();
    useAutoFocusInput(t.inputRef, open && mode === 'new', { delay: 50 });

    useEffect(() => {
        if (!open) return;
        const fallbackMode: Mode = noExistingAuthors ? 'new' : 'existing';
        setMode(fallbackMode);
        setSelectedExisting('');
        t.reset();
        // eslint-disable-next-line react-hooks/exhaustive-deps -- t.reset は useTagsInput 内で useCallback([]) 化され参照が安定（t オブジェクト自体を依存に含めると毎レンダーで再実行されてしまう）
    }, [open, noExistingAuthors, allAuthors]);

    const handleApply = () => {
        let authors: string[];
        if (mode === 'existing') {
            if (!selectedExisting) {
                setError('既存の作者を選択してください。');
                return;
            }
            authors = [selectedExisting];
        } else {
            authors = t.getFinalTags();
            if (authors.length === 0) {
                setError('作者名を 1 つ以上入力してください。');
                return;
            }
        }
        handleSubmit(() => onApply(authors));
    };

    return (
        <Dialog
            open={open}
            title="作者名を一括設定"
            subtitle={`${targetCount} 冊の作者名を上書きします`}
            onClose={onClose}
            maxWidth="md"
            nested
        >
            <DialogBody>
                <div className="space-y-3 mb-2">
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="bulk-author-mode"
                            checked={mode === 'existing'}
                            onChange={() => setMode('existing')}
                            disabled={noExistingAuthors}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存の作者から選択
                                {noExistingAuthors && (
                                    <span className="ml-2 text-xs text-gray-400">
                                        （既存作者なし）
                                    </span>
                                )}
                            </div>
                            {mode === 'existing' && !noExistingAuthors && (
                                <div className="mt-1.5">
                                    <SearchableSelect
                                        value={selectedExisting}
                                        options={allAuthors}
                                        emptyLabel="作者を選択..."
                                        placeholder="作者名で絞り込み"
                                        onChange={setSelectedExisting}
                                    />
                                </div>
                            )}
                        </div>
                    </label>

                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="bulk-author-mode"
                            checked={mode === 'new'}
                            onChange={() => setMode('new')}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                新規作者を作成 / 自由入力
                            </div>
                            {mode === 'new' && (
                                <div className="mt-1.5">
                                    <TagsInput
                                        tags={t.tags}
                                        input={t.input}
                                        inputRef={t.inputRef}
                                        placeholder="作者名を入力（Enter で確定）"
                                        hintText="Enter・カンマで確定、Backspace で削除（複数指定可）"
                                        onChange={t.setInput}
                                        onKeyDown={t.handleKeyDown}
                                        onRemove={t.removeTag}
                                        onBlur={t.handleBlur}
                                    />
                                </div>
                            )}
                        </div>
                    </label>
                </div>

                {error && <p className="mt-3 text-xs text-red-500 dark:text-red-400">{error}</p>}
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
