import type { BookSummary } from '../../features/novel_db/types';

interface Props {
    targetBooks: BookSummary[];
    selectedNames: Set<string>;
    onToggleSelectAll: (books: BookSummary[]) => void;
    onOpenAuthorDialog: () => void;
    onOpenSeriesDialog: () => void;
}

export function BulkActionsPanel({
    targetBooks,
    selectedNames,
    onToggleSelectAll,
    onOpenAuthorDialog,
    onOpenSeriesDialog,
}: Props) {
    const allSelected =
        targetBooks.length > 0 && targetBooks.every((b) => selectedNames.has(b.name));
    const selectedCount = targetBooks.filter((b) => selectedNames.has(b.name)).length;

    return (
        <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-lg text-sm">
            <button
                onClick={() => onToggleSelectAll(targetBooks)}
                className="text-primary-600 dark:text-primary-400 underline text-xs"
            >
                {allSelected ? '全解除' : '全選択'}
            </button>
            <span className="text-gray-600 dark:text-gray-400 text-xs">
                {selectedCount} 冊選択中
            </span>
            <div className="flex gap-2 ml-auto">
                <button
                    disabled={selectedNames.size === 0}
                    onClick={onOpenAuthorDialog}
                    className="px-3 py-1 text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                    作者を設定
                </button>
                <button
                    disabled={selectedNames.size === 0}
                    onClick={onOpenSeriesDialog}
                    className="px-3 py-1 text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                    シリーズに登録
                </button>
            </div>
        </div>
    );
}
