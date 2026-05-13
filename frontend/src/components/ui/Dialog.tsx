import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';

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
 * ダイアログ共通シェル。
 *
 * - 黒オーバーレイ + 中央配置 + 外クリック閉じ + Esc 閉じを共通化する。
 * - z-index は Tailwind config で定義した `z-dialog` / `z-dialog-nested` を使用。
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
    // Esc キーで閉じる
    useEffect(() => {
        if (!open) return;
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [open, onClose]);

    if (!open) return null;

    const zIndexClass = nested ? 'z-dialog-nested' : 'z-dialog';

    return (
        <div
            className={`fixed inset-0 bg-black/50 flex items-center justify-center ${zIndexClass}`}
            onClick={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div
                className={`bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full ${MAX_WIDTH_CLASS[maxWidth]} mx-4 border border-gray-200 dark:border-gray-700 ${className}`}
            >
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                            {title}
                        </h2>
                        {subtitle && (
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                {subtitle}
                            </p>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
                        aria-label="閉じる"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
                {children}
            </div>
        </div>
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
    return <div className={`px-6 py-4 ${className}`}>{children}</div>;
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
