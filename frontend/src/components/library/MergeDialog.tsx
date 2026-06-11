import { useState, useEffect, useRef } from 'react';
import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from '@/components/ui/dialog';
import { validateFilename } from '@/utils/validation';
import { useDialogSubmit } from '@/hooks/library/useDialogSubmit';
import { useAutoFocusInput } from '@/hooks/useAutoFocusInput';

interface MergeDialogProps {
    open: boolean;
    selectedItems: string[]; // 選択中のPDFファイル名（.pdf付き）
    onClose: () => void;
    onMerge: (outputName: string) => Promise<void>;
}

/**
 * PDF結合ダイアログ。
 * 選択中の書籍一覧を表示し、出力ファイル名を入力して結合を実行する。
 */
export function MergeDialog({ open, selectedItems, onClose, onMerge }: MergeDialogProps) {
    const [outputName, setOutputName] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);
    const { saving, error, setError, handleSubmit } = useDialogSubmit(
        onClose,
        '結合に失敗しました。',
    );

    useEffect(() => {
        if (open) {
            setOutputName('');
            setError(null);
        }
    }, [open, setError]);

    useAutoFocusInput(inputRef, open);

    const handleMerge = () => {
        const trimmed = outputName.trim();
        const err = validateFilename(trimmed, 'file');
        if (err) {
            setError(err);
            return;
        }

        const nameWithExt = trimmed.endsWith('.pdf') ? trimmed : `${trimmed}.pdf`;
        handleSubmit(() => onMerge(nameWithExt));
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleMerge();
    };

    return (
        <Dialog open={open} title="PDF を結合" onClose={onClose} maxWidth="md">
            <DialogBody>
                {/* 結合対象一覧 */}
                <div className="mb-4">
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                        結合する書籍（{selectedItems.length} 冊、上から順に結合）:
                    </p>
                    <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1 max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 bg-gray-50 dark:bg-gray-900">
                        {selectedItems.map((name, i) => (
                            <li key={name} className="flex items-center gap-2">
                                <span className="text-gray-400 dark:text-gray-500 tabular-nums w-5 text-right shrink-0">
                                    {i + 1}.
                                </span>
                                <span className="truncate">{name}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                {/* 出力ファイル名入力 */}
                <div className="mb-1">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        出力ファイル名{' '}
                        <span className="text-gray-400 dark:text-gray-500 font-normal">
                            (.pdf は自動付加)
                        </span>
                    </label>
                    <input
                        ref={inputRef}
                        type="text"
                        value={outputName}
                        onChange={(e) => {
                            setOutputName(e.target.value);
                            setError(null);
                        }}
                        onKeyDown={handleKeyDown}
                        placeholder="例: merged_book"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-400 text-sm"
                    />
                </div>
                {error && <p className="text-red-500 dark:text-red-400 text-xs mt-1">{error}</p>}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={handleMerge} disabled={saving || !outputName.trim()}>
                    {saving ? (
                        <span className="flex items-center gap-2">
                            <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                            結合中...
                        </span>
                    ) : (
                        '結合'
                    )}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
