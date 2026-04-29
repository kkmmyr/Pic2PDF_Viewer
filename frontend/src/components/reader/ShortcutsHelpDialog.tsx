import { Dialog, DialogBody } from '../ui/Dialog';

interface ShortcutsHelpDialogProps {
    open: boolean;
    onClose: () => void;
}

const SHORTCUTS: { key: string; description: string }[] = [
    { key: '←  /  →',  description: 'ページ送り（綴じ方向に応じて前後）' },
    { key: 'f',         description: 'フルスクリーン切替' },
    { key: 'e',         description: '編集モード切替' },
    { key: 'Ctrl+F',    description: 'テキスト検索バーを開く' },
    { key: '?',         description: 'このショートカット一覧を開く' },
    { key: 'Esc',       description: '検索バー / フルスクリーンを閉じる' },
];

/**
 * リーダー画面のキーボードショートカット一覧モーダル。
 * `?` キーまたはヘッダーの「?」ボタンから呼ばれる想定。
 */
export function ShortcutsHelpDialog({ open, onClose }: ShortcutsHelpDialogProps) {
    return (
        <Dialog open={open} title="キーボードショートカット" onClose={onClose} maxWidth="md">
            <DialogBody>
                <ul className="space-y-2">
                    {SHORTCUTS.map(({ key, description }) => (
                        <li key={key} className="flex items-center gap-3 text-sm">
                            <kbd className="shrink-0 inline-flex items-center justify-center min-w-[4rem] px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200 font-mono text-xs">
                                {key}
                            </kbd>
                            <span className="text-gray-700 dark:text-gray-300">{description}</span>
                        </li>
                    ))}
                </ul>
            </DialogBody>
        </Dialog>
    );
}
