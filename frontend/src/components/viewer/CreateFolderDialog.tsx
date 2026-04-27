import { useState, useEffect, useRef } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import { validateFilename } from '../../utils/validation';

interface Props {
    open: boolean;
    onClose: () => void;
    onCreate: (name: string) => Promise<void>;
}

/**
 * フォルダ作成ダイアログ。
 * バリデーション（空文字・禁止文字）を行ってから onCreate を呼び出す。
 */
export function CreateFolderDialog({ open, onClose, onCreate }: Props) {
    const [name, setName] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setName('');
            setError(null);
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open]);

    const validationError = validateFilename(name, 'folder');
    const isSubmittable = !validationError && !loading;

    const handleCreate = async () => {
        const err = validateFilename(name, 'folder');
        if (err) { setError(err); return; }
        setLoading(true);
        try {
            await onCreate(name.trim());
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'フォルダの作成に失敗しました。');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && isSubmittable) handleCreate();
    };

    const displayError = error ?? validationError;

    return (
        <Dialog open={open} title="フォルダを作成" onClose={onClose} nested>
            <DialogBody>
                <label htmlFor="folder-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    フォルダ名
                </label>
                <input
                    ref={inputRef}
                    id="folder-name"
                    type="text"
                    value={name}
                    onChange={(e) => { setName(e.target.value); setError(null); }}
                    onKeyDown={handleKeyDown}
                    placeholder="新しいフォルダ"
                    className={`w-full px-3 py-2 rounded-lg border text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 ${
                        displayError ? 'border-red-400 dark:border-red-600' : 'border-gray-300 dark:border-gray-600'
                    }`}
                />
                <p className={`mt-1.5 text-xs min-h-[1rem] ${displayError ? 'text-red-500 dark:text-red-400' : 'text-transparent'}`}>
                    {displayError ?? '　'}
                </p>
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={loading} />
                <DialogPrimaryButton onClick={handleCreate} disabled={!isSubmittable}>
                    {loading ? '作成中...' : '作成'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
