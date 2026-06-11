import { CheckSquare, ChevronRight, Square } from 'lucide-react';

import type { BookSummary } from '@/features/novel_db/types';
import { BulkActionsPanel } from './BulkActionsPanel';
import SeriesDrilldownView from './SeriesDrilldownView';

interface Drilldown {
    seriesId: string;
    label: string;
    books: BookSummary[];
}

interface Props {
    drilldown: Drilldown;
    isSelecting: boolean;
    selectedNames: Set<string>;
    renderCard: (book: BookSummary) => React.ReactNode;
    onBack: () => void;
    onToggleSelecting: () => void;
    onToggleSelectAll: (books: BookSummary[]) => void;
    onOpenAuthorDialog: () => void;
    onOpenSeriesDialog: () => void;
    onOpenDetailBook: (bookName: string) => void;
    onEditBook: (book: BookSummary) => void;
    onReordered: () => void;
}

export function SeriesDrilldownPanel({
    drilldown,
    isSelecting,
    selectedNames,
    renderCard,
    onBack,
    onToggleSelecting,
    onToggleSelectAll,
    onOpenAuthorDialog,
    onOpenSeriesDialog,
    onOpenDetailBook,
    onEditBook,
    onReordered,
}: Props) {
    return (
        <>
            <div className="flex items-center gap-2">
                <nav className="flex items-center gap-1 text-sm flex-1 min-w-0">
                    <button
                        onClick={onBack}
                        className="text-primary-600 dark:text-primary-400 hover:underline font-medium shrink-0"
                    >
                        ライブラリ
                    </button>
                    <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="text-gray-900 dark:text-gray-100 font-medium truncate">
                        {drilldown.label}
                    </span>
                    <span className="text-gray-400 dark:text-gray-500 text-xs ml-1 shrink-0">
                        ({drilldown.books.length} 冊)
                    </span>
                </nav>
                <button
                    onClick={onToggleSelecting}
                    className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                        isSelecting
                            ? 'bg-primary-100 dark:bg-primary-900/40 border-primary-400 text-primary-700 dark:text-primary-300'
                            : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                >
                    {isSelecting ? (
                        <CheckSquare className="w-3.5 h-3.5" />
                    ) : (
                        <Square className="w-3.5 h-3.5" />
                    )}
                    選択
                </button>
            </div>

            {isSelecting && (
                <BulkActionsPanel
                    targetBooks={drilldown.books}
                    selectedNames={selectedNames}
                    onToggleSelectAll={onToggleSelectAll}
                    onOpenAuthorDialog={onOpenAuthorDialog}
                    onOpenSeriesDialog={onOpenSeriesDialog}
                />
            )}

            {isSelecting ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                    {drilldown.books.map(renderCard)}
                </div>
            ) : (
                <SeriesDrilldownView
                    seriesId={drilldown.seriesId}
                    books={drilldown.books}
                    onOpenDetailBook={onOpenDetailBook}
                    onEditBook={onEditBook}
                    onReordered={onReordered}
                />
            )}
        </>
    );
}
