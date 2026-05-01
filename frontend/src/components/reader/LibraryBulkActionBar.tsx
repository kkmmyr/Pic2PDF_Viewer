import { User, Tag, Library, Layers, Eye, EyeOff, Merge, ImageIcon, Trash2 } from 'lucide-react';

const BTN_PRIMARY = 'px-3 py-1.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5';
const BTN_SECONDARY = 'px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 flex items-center gap-1.5';
const BTN_DANGER = 'px-3 py-1.5 bg-red-600 text-white rounded-md text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5';

interface LibraryBulkActionBarProps {
    selectedCount: number;
    showHidden: boolean;
    bulkSeriesDisabled?: boolean;
    onBulkSetAuthor: () => void;
    onBulkSetTag: () => void;
    onBulkSetSeries: () => void;
    onBulkSetGenre: () => void;
    onBulkToggleHidden: () => void;
    onBulkDelete: () => void;
    onMergePdfs: () => void;
    onRegenThumbnailBulk: () => void;
    onToggleSelectionMode: () => void;
}

export function LibraryBulkActionBar({
    selectedCount,
    showHidden,
    bulkSeriesDisabled,
    onBulkSetAuthor,
    onBulkSetTag,
    onBulkSetSeries,
    onBulkSetGenre,
    onBulkToggleHidden,
    onBulkDelete,
    onMergePdfs,
    onRegenThumbnailBulk,
    onToggleSelectionMode,
}: LibraryBulkActionBarProps) {
    return (
        <div className="h-11 flex items-center px-4 gap-2 border-t border-gray-100 dark:border-gray-800 bg-indigo-50/50 dark:bg-indigo-900/10">
            <span className="text-sm font-medium mr-2 text-gray-700 dark:text-gray-300 shrink-0">
                {selectedCount} 選択中
            </span>
            <button onClick={onBulkSetAuthor} disabled={selectedCount === 0} className={BTN_PRIMARY}>
                <User className="w-4 h-4" />
                作者を設定
            </button>
            <button onClick={onBulkSetTag} disabled={selectedCount === 0} title="選択した書籍のタグを一括設定" className={BTN_PRIMARY}>
                <Tag className="w-4 h-4" />
                タグを設定
            </button>
            <button onClick={onBulkSetSeries} disabled={selectedCount === 0 || !!bulkSeriesDisabled} title={bulkSeriesDisabled ? '複数の異なる作者が混在しているためシリーズ登録できません' : '選択した書籍をシリーズに一括登録（選択順に採番）'} className={BTN_PRIMARY}>
                <Library className="w-4 h-4" />
                シリーズに登録
            </button>
            <button onClick={onBulkSetGenre} disabled={selectedCount === 0} title="選択した書籍のジャンルを一括設定" className={BTN_PRIMARY}>
                <Layers className="w-4 h-4" />
                ジャンルを設定
            </button>
            <button
                onClick={onBulkToggleHidden}
                disabled={selectedCount === 0}
                title={showHidden ? '選択した書籍を再表示' : '選択した書籍を非表示'}
                className={BTN_PRIMARY}
            >
                {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                {showHidden ? 'まとめて再表示' : 'まとめて非表示'}
            </button>
            {showHidden && (
                <button
                    onClick={onBulkDelete}
                    disabled={selectedCount === 0}
                    title="選択した書籍をディスクから完全に削除する（元に戻せません）"
                    className={BTN_DANGER}
                >
                    <Trash2 className="w-4 h-4" />
                    完全削除
                </button>
            )}
            <button onClick={onMergePdfs} disabled={selectedCount < 2} title="選択した書籍を1つのPDFに結合" className={BTN_PRIMARY}>
                <Merge className="w-4 h-4" />
                結合
            </button>
            <button onClick={onRegenThumbnailBulk} disabled={selectedCount === 0} title="選択した書籍のサムネイルを再生成" className={BTN_PRIMARY}>
                <ImageIcon className="w-4 h-4" />
                サムネイル再生成
            </button>
            <div className="flex-1" />
            <button onClick={onToggleSelectionMode} className={BTN_SECONDARY}>
                キャンセル
            </button>
        </div>
    );
}
