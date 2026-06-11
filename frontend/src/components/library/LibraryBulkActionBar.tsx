import { User, Library, Layers, Eye, EyeOff, Merge, ImageIcon, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface LibraryBulkActionBarProps {
    selectedCount: number;
    showHidden: boolean;
    bulkSeriesDisabled?: boolean;
    onBulkSetAuthor: () => void;
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
    onBulkSetSeries,
    onBulkSetGenre,
    onBulkToggleHidden,
    onBulkDelete,
    onMergePdfs,
    onRegenThumbnailBulk,
    onToggleSelectionMode,
}: LibraryBulkActionBarProps) {
    const noSelection = selectedCount === 0;
    return (
        <div className="h-11 flex items-center px-4 gap-2 border-t border-gray-100 dark:border-gray-800 bg-primary-50/50 dark:bg-primary-900/10">
            <span className="text-sm font-medium mr-2 text-gray-700 dark:text-gray-300 shrink-0">
                {selectedCount} 選択中
            </span>
            <Button onClick={onBulkSetAuthor} disabled={noSelection}>
                <User className="w-4 h-4" />
                作者を設定
            </Button>
            <Button
                onClick={onBulkSetSeries}
                disabled={noSelection || !!bulkSeriesDisabled}
                title={
                    bulkSeriesDisabled
                        ? '複数の異なる作者が混在しているためシリーズ登録できません'
                        : '選択した書籍をシリーズに一括登録（選択順に採番）'
                }
            >
                <Library className="w-4 h-4" />
                シリーズに登録
            </Button>
            <Button
                onClick={onBulkSetGenre}
                disabled={noSelection}
                title="選択した書籍のジャンルを一括設定"
            >
                <Layers className="w-4 h-4" />
                ジャンルを設定
            </Button>
            <Button
                onClick={onBulkToggleHidden}
                disabled={noSelection}
                title={showHidden ? '選択した書籍を再表示' : '選択した書籍を非表示'}
            >
                {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                {showHidden ? 'まとめて再表示' : 'まとめて非表示'}
            </Button>
            {showHidden && (
                <Button
                    variant="danger"
                    onClick={onBulkDelete}
                    disabled={noSelection}
                    title="選択した書籍をディスクから完全に削除する（元に戻せません）"
                >
                    <Trash2 className="w-4 h-4" />
                    完全削除
                </Button>
            )}
            <Button
                onClick={onMergePdfs}
                disabled={selectedCount < 2}
                title="選択した書籍を1つのPDFに結合"
            >
                <Merge className="w-4 h-4" />
                結合
            </Button>
            <Button
                onClick={onRegenThumbnailBulk}
                disabled={noSelection}
                title="選択した書籍のサムネイルを再生成"
            >
                <ImageIcon className="w-4 h-4" />
                サムネイル再生成
            </Button>
            <div className="flex-1" />
            <Button variant="secondary" onClick={onToggleSelectionMode}>
                キャンセル
            </Button>
        </div>
    );
}
