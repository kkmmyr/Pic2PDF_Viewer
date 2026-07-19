import { memo } from 'react';
import { Dialog, DialogBody } from '@/components/ui/dialog';
import { useReaderField } from '@/contexts/ReaderContext';

const SHORTCUTS: { key: string; description: string }[] = [
    { key: '←  /  →', description: 'ページ送り（綴じ方向に応じて前後）' },
    { key: '↓  /  ↑', description: '次の巻 / 前の巻へ移動（シリーズ登録済みの場合）' },
    { key: 'f', description: 'フルスクリーン切替' },
    { key: 'e', description: '編集モード切替' },
    { key: 'Ctrl+F', description: 'テキスト検索バーを開く' },
    { key: '?', description: 'このショートカット一覧を開く' },
    { key: 'Esc', description: '検索バー / フルスクリーンを閉じる' },
];

/**
 * リーダー画面のキーボードショートカット一覧モーダル。
 * `?` キーまたはヘッダーの「?」ボタンから呼ばれる想定。
 */
export const ShortcutsHelpDialog = memo(function ShortcutsHelpDialog() {
    const isHelpOpen = useReaderField('isHelpOpen');
    const closeHelp = useReaderField('closeHelp');
    return (
        <Dialog
            open={isHelpOpen}
            title="キーボードショートカット"
            onClose={closeHelp}
            maxWidth="md"
        >
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
});
