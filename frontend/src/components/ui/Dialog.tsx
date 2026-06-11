import * as RadixDialog from '@radix-ui/react-dialog';
import { type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

type DialogMaxWidth = 'sm' | 'md' | 'xl';

interface DialogProps {
    open: boolean;
    title: string;
    /** ヘッダー右上のサブテキスト（例: "3 冊の作者名を上書きします"） */
    subtitle?: string;
    /** ネストダイアログとして上層に表示する場合 true */
    nested?: boolean;
    /** dialog 横幅: sm = max-w-sm（デフォルト）/ md = max-w-md / xl = max-w-4xl */
    maxWidth?: DialogMaxWidth;
    /** 内部パネルへの追加 Tailwind クラス（flex / max-h などの調整用） */
    className?: string;
    onClose: () => void;
    children: ReactNode;
}

const MAX_WIDTH_CLASS: Record<DialogMaxWidth, string> = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    xl: 'max-w-4xl',
};

/**
 * ダイアログ共通シェル。Radix Dialog を内部で使用し、フォーカストラップ・
 * スクロールロック・ポータルレンダリングを提供する。
 *
 * 使用例:
 * ```tsx
 * <Dialog open={open} title="フォルダを作成" onClose={onClose}>
 *     <DialogBody>...</DialogBody>
 *     <DialogFooter>
 *         <DialogCancelButton onClick={onClose} />
 *         <DialogPrimaryButton onClick={handleCreate}>作成</DialogPrimaryButton>
 *     </DialogFooter>
 * </Dialog>
 * ```
 */
export function Dialog({
    open,
    title,
    subtitle,
    nested = false,
    maxWidth = 'sm',
    className = '',
    onClose,
    children,
}: DialogProps) {
    const zClass = nested ? 'z-dialog-nested' : 'z-dialog';

    return (
        <RadixDialog.Root
            open={open}
            onOpenChange={(o) => {
                if (!o) onClose();
            }}
        >
            <RadixDialog.Portal>
                <RadixDialog.Overlay
                    data-testid="dialog-overlay"
                    className={cn('fixed inset-0 bg-black/50', zClass)}
                    onClick={() => onClose()}
                />
                <RadixDialog.Content
                    className={cn(
                        'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
                        'bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full mx-4',
                        'border border-gray-200 dark:border-gray-700',
                        MAX_WIDTH_CLASS[maxWidth],
                        zClass,
                        className,
                    )}
                    onInteractOutside={(e) => e.preventDefault()}
                >
                    <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                        <div>
                            <RadixDialog.Title className="text-base font-semibold text-gray-900 dark:text-gray-100">
                                {title}
                            </RadixDialog.Title>
                            {subtitle && (
                                <RadixDialog.Description className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                    {subtitle}
                                </RadixDialog.Description>
                            )}
                        </div>
                        <RadixDialog.Close asChild>
                            <button
                                className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
                                aria-label="閉じる"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </RadixDialog.Close>
                    </div>
                    {children}
                </RadixDialog.Content>
            </RadixDialog.Portal>
        </RadixDialog.Root>
    );
}

/** ダイアログ本体（パディング付き）。タイトル/フッターと挟む形で使う。 */
export function DialogBody({
    children,
    className = '',
}: {
    children: ReactNode;
    className?: string;
}) {
    return <div className={cn('px-6 py-4', className)}>{children}</div>;
}

/** ダイアログ下部のボタン領域（ボーダー + 右寄せ flex）。 */
export function DialogFooter({ children }: { children: ReactNode }) {
    return (
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
            {children}
        </div>
    );
}

interface DialogButtonProps {
    onClick: () => void;
    disabled?: boolean;
    children?: ReactNode;
}

/** キャンセル系ボタン（ダイアログ用専用サイズ: px-4 py-2 rounded-lg）。 */
export function DialogCancelButton({
    onClick,
    disabled,
    children = 'キャンセル',
}: DialogButtonProps) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 transition-colors"
        >
            {children}
        </button>
    );
}

/** プライマリ確定ボタン（ダイアログ用専用サイズ: px-4 py-2 rounded-lg）。色は primary token。 */
export function DialogPrimaryButton({ onClick, disabled, children }: DialogButtonProps) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 dark:disabled:bg-primary-900 rounded-lg transition-colors"
        >
            {children}
        </button>
    );
}
