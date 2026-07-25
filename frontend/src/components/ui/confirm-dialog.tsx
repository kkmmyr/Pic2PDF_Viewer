import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { cn } from '@/lib/utils';

interface ConfirmDialogProps {
    open: boolean;
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    confirmDisabled?: boolean;
    /** true: 危険操作（赤系のスタイル） */
    danger?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

/**
 * 汎用確認ダイアログ。Radix AlertDialog ベース（フォーカストラップ・a11y 対応済み）。
 * OS ネイティブ `confirm()` の置換用。
 */
export function ConfirmDialog({
    open,
    title,
    message,
    confirmLabel = '実行',
    cancelLabel = 'キャンセル',
    confirmDisabled = false,
    danger = false,
    onConfirm,
    onCancel,
}: ConfirmDialogProps) {
    return (
        <AlertDialog.Root
            open={open}
            onOpenChange={(o) => {
                if (!o) onCancel();
            }}
        >
            <AlertDialog.Portal>
                <AlertDialog.Overlay
                    data-testid="confirm-dialog-overlay"
                    className="fixed inset-0 bg-black/50 z-dialog-nested"
                />
                <AlertDialog.Content
                    className={cn(
                        'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
                        'bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-sm mx-4',
                        'border border-gray-200 dark:border-gray-700 z-dialog-nested',
                    )}
                >
                    <div className="px-6 pt-6 pb-2">
                        <AlertDialog.Title className="text-base font-semibold text-gray-900 dark:text-gray-100">
                            {title}
                        </AlertDialog.Title>
                    </div>
                    <div className="px-6 py-4">
                        <AlertDialog.Description asChild>
                            <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-line">
                                {message}
                            </p>
                        </AlertDialog.Description>
                    </div>
                    <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
                        <AlertDialog.Cancel asChild>
                            <button
                                type="button"
                                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 transition-colors"
                            >
                                {cancelLabel}
                            </button>
                        </AlertDialog.Cancel>
                        <AlertDialog.Action asChild>
                            <button
                                type="button"
                                onClick={onConfirm}
                                disabled={confirmDisabled}
                                className={cn(
                                    'px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors',
                                    danger
                                        ? 'bg-red-600 hover:bg-red-700'
                                        : 'bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 dark:disabled:bg-primary-900',
                                )}
                            >
                                {confirmLabel}
                            </button>
                        </AlertDialog.Action>
                    </div>
                </AlertDialog.Content>
            </AlertDialog.Portal>
        </AlertDialog.Root>
    );
}
