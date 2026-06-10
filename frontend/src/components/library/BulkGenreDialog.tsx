import { useState, useEffect, useRef } from 'react';
import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from '../ui/Dialog';
import { useDialogSubmit } from '../../hooks/library/useDialogSubmit';

interface BulkGenreDialogProps {
    open: boolean;
    targetCount: number;
    allGenres: string[];
    onClose: () => void;
    onApply: (genre: string) => Promise<void>;
}

export function BulkGenreDialog({
    open,
    targetCount,
    allGenres,
    onClose,
    onApply,
}: BulkGenreDialogProps) {
    const [selected, setSelected] = useState<string>(allGenres[0] ?? '');
    const [isNew, setIsNew] = useState(false);
    const [newGenre, setNewGenre] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);
    const { saving, error, setError, handleSubmit } = useDialogSubmit(onClose);

    useEffect(() => {
        if (!open) return;
        setSelected(allGenres[0] ?? '');
        setIsNew(false);
        setNewGenre('');
    }, [open, allGenres]);

    const handleApply = () => {
        const genre = isNew ? newGenre.trim() : selected;
        if (!genre) {
            setError('ジャンルを選択または入力してください。');
            return;
        }
        handleSubmit(() => onApply(genre));
    };

    return (
        <Dialog
            open={open}
            title="ジャンルを一括設定"
            subtitle={`${targetCount} 冊のジャンルを上書きします`}
            onClose={onClose}
            maxWidth="sm"
            nested
        >
            <DialogBody>
                <div className="space-y-2 mb-2">
                    {allGenres.map((genre) => (
                        <label key={genre} className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="radio"
                                name="bulk-genre"
                                checked={!isNew && selected === genre}
                                onChange={() => {
                                    setIsNew(false);
                                    setSelected(genre);
                                }}
                                className="accent-primary-600"
                            />
                            <span className="text-sm text-gray-800 dark:text-gray-200">
                                {genre}
                            </span>
                        </label>
                    ))}
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="bulk-genre"
                            checked={isNew}
                            onChange={() => {
                                setIsNew(true);
                                setTimeout(() => inputRef.current?.focus(), 50);
                            }}
                            className="mt-0.5 accent-primary-600"
                        />
                        <div className="flex-1">
                            <span className="text-sm text-gray-800 dark:text-gray-200">
                                新規ジャンルを入力
                            </span>
                            {isNew && (
                                <input
                                    ref={inputRef}
                                    type="text"
                                    value={newGenre}
                                    onChange={(e) => setNewGenre(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') handleApply();
                                    }}
                                    placeholder="ジャンル名"
                                    className="mt-1.5 block w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                                />
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
