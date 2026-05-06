import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from './Dialog';

interface ConfirmDialogProps {
    open: boolean;
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    /** true: 危険操作（赤系のスタイル） */
    danger?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

/**
 * 汎用確認ダイアログ。OS ネイティブ `confirm()` の置換用。
 *
 * `Dialog` 共通シェルをベースに、ユーザーへ「実行/キャンセル」の選択を求める。
 */
export function ConfirmDialog({
    open,
    title,
    message,
    confirmLabel = '実行',
    cancelLabel = 'キャンセル',
    danger = false,
    onConfirm,
    onCancel,
}: ConfirmDialogProps) {
    return (
        <Dialog open={open} title={title} onClose={onCancel} nested>
            <DialogBody>
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-line">
                    {message}
                </p>
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onCancel}>{cancelLabel}</DialogCancelButton>
                {danger ? (
                    <button
                        onClick={onConfirm}
                        className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
                    >
                        {confirmLabel}
                    </button>
                ) : (
                    <DialogPrimaryButton onClick={onConfirm}>{confirmLabel}</DialogPrimaryButton>
                )}
            </DialogFooter>
        </Dialog>
    );
}
