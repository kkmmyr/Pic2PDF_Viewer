import { useState, useRef, useEffect } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import { validateFilename } from '../../utils/validation';
import { useDialogSubmit } from '../../hooks/useDialogSubmit';
import { useAutoFocusInput } from '../../hooks/useAutoFocusInput';

interface Props {
    open: boolean;
    currentName: string;  // PDF の場合は .pdf 拡張子あり、フォルダの場合は拡張子なし
    isFolder?: boolean;
    onClose: () => void;
    onRename: (newName: string) => Promise<void>;
}

/**
 * PDF/フォルダ共用リネームダイアログ。
 * PDF の場合は拡張子 .pdf を表示から省き、確定時に自動付加する。
 */
export function RenameDialog({ open, currentName, isFolder = false, onClose, onRename }: Props) {
    const stem = isFolder ? currentName : currentName.replace(/\.pdf$/i, '');
    const [name, setName] = useState(stem);
    const inputRef = useRef<HTMLInputElement>(null);
    const { saving, error, setError, handleSubmit } = useDialogSubmit(onClose, 'リネームに失敗しました。');

    useEffect(() => {
        if (open) {
            setName(stem);
            setError(null);
        }
    }, [open, stem, setError]);

    useAutoFocusInput(inputRef, open, { delay: 50, select: true });

    const validationError = validateFilename(name, isFolder ? 'folder' : 'file');
    const isSubmittable = !validationError && !saving && name.trim() !== stem;

    const handleRename = () => {
        const err = validateFilename(name, isFolder ? 'folder' : 'file');
        if (err) { setError(err); return; }
        if (name.trim() === stem) { onClose(); return; }
        handleSubmit(() => onRename(isFolder ? name.trim() : name.trim() + '.pdf'));
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && isSubmittable) handleRename();
    };

    const displayError = error ?? validationError;

    return (
        <Dialog open={open} title="名前を変更" onClose={onClose} nested>
            <DialogBody>
                <label htmlFor="rename-input" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    新しい名前
                </label>
                <div className="flex items-center gap-1">
                    <input
                        ref={inputRef}
                        id="rename-input"
                        type="text"
                        value={name}
                        onChange={(e) => { setName(e.target.value); setError(null); }}
                        onKeyDown={handleKeyDown}
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-blue-500 ${
                            displayError ? 'border-red-400 dark:border-red-600' : 'border-gray-300 dark:border-gray-600'
                        }`}
                    />
                    {!isFolder && (
                        <span className="text-sm text-gray-400 dark:text-gray-500 shrink-0">.pdf</span>
                    )}
                </div>
                <p className={`mt-1.5 text-xs min-h-[1rem] ${displayError ? 'text-red-500 dark:text-red-400' : 'text-transparent'}`}>
                    {displayError ?? '　'}
                </p>
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={handleRename} disabled={!isSubmittable}>
                    {saving ? '変更中...' : '変更'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
