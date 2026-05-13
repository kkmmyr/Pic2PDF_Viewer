import { useEffect, useState } from 'react';

import { useAutoFocusInput } from '../../hooks/useAutoFocusInput';
import { useDialogSubmit } from '../../hooks/useDialogSubmit';
import { useTagsInput } from '../../hooks/useTagsInput';
import { Dialog, DialogBody, DialogCancelButton, DialogFooter, DialogPrimaryButton } from '../ui/Dialog';
import { SearchableSelect } from '../ui/SearchableSelect';
import { TagsInput } from '../ui/TagsInput';

interface Props {
    open: boolean;
    targetCount: number;
    allAuthors: string[];
    onClose: () => void;
    /** 選択した書籍全冊に authors を適用する（呼び出し元が PATCH を順次実行） */
    onApply: (authors: string[]) => Promise<void>;
}

type Mode = 'existing' | 'new';

/**
 * 小説 DB 用: 複数冊への作者名一括設定ダイアログ（B-21）。
 * doujin 用 BulkAuthorDialog の小説専用版。
 */
export function NovelBulkAuthorDialog({ open, targetCount, allAuthors, onClose, onApply }: Props) {
    const noExisting = allAuthors.length === 0;
    const [mode, setMode] = useState<Mode>(noExisting ? 'new' : 'existing');
    const [selectedExisting, setSelectedExisting] = useState<string>('');
    const { saving, error, setError, handleSubmit } = useDialogSubmit(onClose);
    const t = useTagsInput();
    useAutoFocusInput(t.inputRef, open && mode === 'new', { delay: 50 });

    useEffect(() => {
        if (!open) return;
        setMode(noExisting ? 'new' : 'existing');
        setSelectedExisting(allAuthors[0] ?? '');
        t.reset();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, noExisting, allAuthors]);

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
                            name="novel-bulk-author-mode"
                            checked={mode === 'existing'}
                            onChange={() => setMode('existing')}
                            disabled={noExisting}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存の作者から選択
                                {noExisting && (
                                    <span className="ml-2 text-xs text-gray-400">（既存作者なし）</span>
                                )}
                            </div>
                            {mode === 'existing' && !noExisting && (
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
                            name="novel-bulk-author-mode"
                            checked={mode === 'new'}
                            onChange={() => setMode('new')}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                新規作者を入力
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
