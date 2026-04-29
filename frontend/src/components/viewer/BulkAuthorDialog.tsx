import { useState, useRef, KeyboardEvent, useEffect } from 'react';
import { X } from 'lucide-react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import { SearchableSelect } from '../ui/SearchableSelect';

interface BulkAuthorDialogProps {
    open: boolean;
    targetCount: number;       // 選択中の書籍数
    /** 既存の作者一覧。空配列なら「既存から選択」モードは無効 */
    allAuthors: string[];
    onClose: () => void;
    onApply: (authors: string[]) => Promise<void>;
}

type Mode = 'existing' | 'new';

/**
 * 複数書籍への作者名一括設定ダイアログ。
 * 設定した作者名で選択中の全書籍を上書きする。
 *
 * - 既存モード: SearchableSelect から 1 名選択（同じ作者の本を増やす用途）
 * - 新規モード: chip 入力で複数の作者名を Enter / カンマ区切りで追加
 */
export function BulkAuthorDialog({ open, targetCount, allAuthors, onClose, onApply }: BulkAuthorDialogProps) {
    const noExistingAuthors = allAuthors.length === 0;
    const [mode, setMode] = useState<Mode>(noExistingAuthors ? 'new' : 'existing');
    const [selectedExisting, setSelectedExisting] = useState<string>('');

    // 新規モード（chip 入力）の状態
    const [tags, setTags] = useState<string[]>([]);
    const [input, setInput] = useState('');

    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (!open) return;
        const fallbackMode: Mode = noExistingAuthors ? 'new' : 'existing';
        setMode(fallbackMode);
        setSelectedExisting(allAuthors[0] ?? '');
        setTags([]);
        setInput('');
        setError(null);
        if (fallbackMode === 'new') {
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open, noExistingAuthors, allAuthors]);

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
        setError(null);

        let authors: string[];
        if (mode === 'existing') {
            if (!selectedExisting) {
                setError('既存の作者を選択してください。');
                return;
            }
            authors = [selectedExisting];
        } else {
            const finalTags = input.trim() ? [...tags, input.trim()] : tags;
            authors = [...new Set(finalTags)];
            if (authors.length === 0) {
                setError('作者名を 1 つ以上入力してください。');
                return;
            }
        }

        setSaving(true);
        try {
            await onApply(authors);
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
                            className="mt-1 accent-blue-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存の作者から選択
                                {noExistingAuthors && (
                                    <span className="ml-2 text-xs text-gray-400">（既存作者なし）</span>
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
                            onChange={() => {
                                setMode('new');
                                setTimeout(() => inputRef.current?.focus(), 50);
                            }}
                            className="mt-1 accent-blue-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                新規作者を作成 / 自由入力
                            </div>
                            {mode === 'new' && (
                                <>
                                    <div
                                        className="mt-1.5 min-h-[2.5rem] w-full flex flex-wrap gap-1.5 px-2.5 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 cursor-text"
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
                                        Enter・カンマで確定、Backspace で削除（複数指定可）
                                    </p>
                                </>
                            )}
                        </div>
                    </label>
                </div>

                {error && (
                    <p className="mt-3 text-xs text-red-500 dark:text-red-400">{error}</p>
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
